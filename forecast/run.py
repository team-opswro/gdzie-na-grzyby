"""Dzienny przebieg: pobranie pogody, wyliczenie mnożników w i atomowy zapis pogoda.json."""
import argparse
import gzip
import json
import logging
import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import jsonschema
import requests

from forecast.model import DailySeries, limiting_factor, weather_multiplier, weather_values
from forecast.species import ROOT, Species, load_species
from forecast.weather import WeatherError, fetch_series

log = logging.getLogger("forecast.run")

SCHEMA_PATH = ROOT / "schema/pogoda.schema.json"
DAYS = 7
PAST_DAYS = 1
DIGITS = 3
TZ = ZoneInfo("Europe/Warsaw")
S3_ENV = ("S3_ENDPOINT", "S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY")
LIVE_KEY = "live/pogoda.json"
MARKER = "last_upload"


class ConfigError(Exception):
    pass


def state_dir() -> Path:
    return Path(os.environ.get("STATE_DIR", "/state"))


def _json_body(content: bytes):
    if content[:2] == b"\x1f\x8b":
        content = gzip.decompress(content)
    return json.loads(content)


def fetch_grid(data_base_url: str, session) -> list[dict]:
    """manifest.json -> grid.json z publicznego DATA_BASE_URL; zwraca listę komórek."""
    base = data_base_url if data_base_url.endswith("/") else data_base_url + "/"

    def get(path):
        r = session.get(base + path, timeout=60)
        r.raise_for_status()
        return _json_body(r.content)

    manifest = get("manifest.json")
    return get(manifest["base"] + manifest["files"]["grid"])["cells"]


def make_client():
    import boto3
    from botocore.config import Config

    missing = [k for k in S3_ENV if not os.environ.get(k)]
    if missing:
        raise ConfigError("brak zmiennych środowiska: " + ", ".join(missing))
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT"],
        region_name=os.environ.get("S3_REGION", "auto"),
        aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def upload_pogoda(client, bucket: str, path: Path) -> None:
    client.put_object(
        Bucket=bucket, Key=LIVE_KEY, Body=gzip.compress(Path(path).read_bytes(), mtime=0),
        ContentType="application/json", ContentEncoding="gzip", CacheControl="no-cache",
    )


def write_marker() -> None:
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / MARKER).write_text(datetime.now(TZ).isoformat(timespec="seconds"))


def build_payload(cells: list[dict], series: dict[str, DailySeries], species: dict[str, Species],
                  today: date, now: datetime) -> dict:
    days = [today + timedelta(days=k) for k in range(-PAST_DAYS, DAYS)]
    out: dict[str, dict] = {}
    wx: dict[str, dict] = {}
    for cell in cells:
        cid = cell["id"]
        s = series[cid]
        missing = [d for d in days if d not in s.dates]
        if missing:
            raise ValueError(f"komórka {cid}: brak dni {[d.isoformat() for d in missing]}")
        idx = [s.dates.index(d) for d in days]
        per_species = {}
        for key, sp in species.items():
            comps = [weather_multiplier(s, i, sp) for i in idx]
            per_species[key] = {
                name: [round(getattr(c, name), DIGITS) for c in comps]
                for name in ("w", "rain", "temp", "season")
            }
            per_species[key]["lim"] = [
                limiting_factor(c, s, i, sp) for c, i in zip(comps, idx)
            ]
        out[cid] = per_species
        vals = [weather_values(s, i) for i in idx]
        wx[cid] = {
            "rain_mm": [round(v.rain_mm, 1) for v in vals],
            "soil_t": [round(v.soil_t, 1) for v in vals],
            "soil_m": [round(v.soil_m, 3) for v in vals],
        }
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "days": [d.isoformat() for d in days],
        "wx": wx,
        "cells": out,
    }


def write_atomic(payload: dict, out: Path, schema: Path = SCHEMA_PATH) -> None:
    tmp = out.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False))
        validator = jsonschema.Draft202012Validator(
            json.loads(schema.read_text()), format_checker=jsonschema.FormatChecker()
        )
        validator.validate(json.loads(tmp.read_text()))
        os.replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generuje pogoda.json")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--grid", type=Path, help="lokalny grid.json (dev/testy)")
    src.add_argument("--grid-from-url", action="store_true",
                     help="grid z manifestu pod DATA_BASE_URL")
    parser.add_argument("--out", type=Path, help="lokalny plik wyjściowy")
    parser.add_argument("--upload", action="store_true",
                        help="wyślij do live/pogoda.json (env S3_*)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(message)s")
    if not args.out and not args.upload:
        parser.error("podaj --out i/lub --upload")

    now = datetime.now(TZ)
    today = now.date()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = args.out or Path(tmp) / "pogoda.json"
            client = bucket = None
            if args.upload:
                client = make_client()
                bucket = os.environ["S3_BUCKET"]
            if args.grid_from_url:
                base = os.environ.get("DATA_BASE_URL")
                if not base:
                    raise ConfigError("brak DATA_BASE_URL")
                cells = fetch_grid(base, requests.Session())
            else:
                cells = json.loads(args.grid.read_text())["cells"]
            points = [(c["id"], c["lat"], c["lon"]) for c in cells]
            log.info("pobieranie pogody dla %d komórek", len(points))
            series = fetch_series(points)
            payload = build_payload(cells, series, load_species(), today, now)
            write_atomic(payload, out)
            if args.upload:
                upload_pogoda(client, bucket, out)
                write_marker()
                log.info("wysłano %s", LIVE_KEY)
    except (WeatherError, ValueError, ConfigError, jsonschema.ValidationError) as e:
        log.error("nie wygenerowano pogoda.json: %s", e)
        return 1
    except Exception:
        log.exception("nieoczekiwany błąd, nie wygenerowano pogoda.json")
        return 1
    log.info("gotowe (%d komórek)", len(cells))
    return 0


if __name__ == "__main__":
    sys.exit(main())
