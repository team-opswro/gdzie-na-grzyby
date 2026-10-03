"""Dzienny przebieg: pobranie pogody, wyliczenie mnożników w i atomowy zapis pogoda.json."""
import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import jsonschema

from forecast.model import DailySeries, weather_multiplier
from forecast.species import ROOT, Species, load_species
from forecast.weather import WeatherError, fetch_series

log = logging.getLogger("forecast.run")

SCHEMA_PATH = ROOT / "schema/pogoda.schema.json"
DAYS = 7
DIGITS = 3
TZ = ZoneInfo("Europe/Warsaw")


def build_payload(cells: list[dict], series: dict[str, DailySeries], species: dict[str, Species],
                  today: date, now: datetime) -> dict:
    days = [today + timedelta(days=k) for k in range(DAYS)]
    out: dict[str, dict] = {}
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
        out[cid] = per_species
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "days": [d.isoformat() for d in days],
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
    parser.add_argument("--grid", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(message)s")

    now = datetime.now(TZ)
    today = now.date()
    try:
        cells = json.loads(args.grid.read_text())["cells"]
        points = [(c["id"], c["lat"], c["lon"]) for c in cells]
        log.info("pobieranie pogody dla %d komórek", len(points))
        series = fetch_series(points)
        payload = build_payload(cells, series, load_species(), today, now)
        write_atomic(payload, args.out)
    except (WeatherError, ValueError, jsonschema.ValidationError) as e:
        log.error("nie wygenerowano pogoda.json: %s", e)
        return 1
    log.info("zapisano %s (%d komórek)", args.out, len(cells))
    return 0


if __name__ == "__main__":
    sys.exit(main())
