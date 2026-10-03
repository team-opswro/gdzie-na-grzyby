"""Pobieranie wydzieleń BDL (OGC API Features) i wczytanie ich do GeoDataFrame."""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
import yaml

from pipeline.habitat import normalize_habitat, normalize_species_code

ROOT = Path(__file__).resolve().parent.parent
FIELDS_YAML = Path(__file__).resolve().parent / "bdl_fields.yaml"
RAW_DIR = Path(__file__).resolve().parent / "data" / "raw"

DEFAULT_BASE_URL = "https://ogcapi.bdl.lasy.gov.pl"
PAGE_LIMIT = 1000
TIMEOUT = 120
RETRIES = 4
OUT_COLUMNS = ["id", "sp_main", "sp_admix", "age", "hab", "fun"]


def _none_if_na(value):
    return None if pd.isna(value) else value


def _fun_value(value):
    if pd.isna(value):
        return None
    value = str(value).strip()
    return value or None


def load_bdl(src: Path, fields: dict) -> gpd.GeoDataFrame:
    """Wczytuje wszystkie *.geojson i *.gpkg z `src`, zostawia same drzewostany.

    `fields` to konfiguracja z bdl_fields.yaml (klucze `fields` i `forest_filter`).
    Wynik: id, sp_main, sp_admix (tuple), age (Int64), hab, fun (forest_fun lub None), geometry; EPSG:4326.
    """
    cols = fields["fields"]
    flt = fields.get("forest_filter") or {}
    files = sorted(Path(src).glob("*.geojson")) + sorted(Path(src).glob("*.gpkg"))
    frames = []
    for path in files:
        df = gpd.read_file(path)
        if df.crs is None:
            df = df.set_crs(4326)
        frames.append(df.to_crs(4326))
    if not frames:
        raise FileNotFoundError(f"Brak plików *.geojson/*.gpkg w {src}")
    df = pd.concat(frames, ignore_index=True)

    if flt.get("column"):
        df = df[df[flt["column"]].isin(flt["values"])]
    for col in flt.get("require_not_null", []):
        df = df[df[col].notna() & (df[col].astype(str).str.strip() != "")]

    out = gpd.GeoDataFrame(
        {
            "id": df[cols["id"]].astype(str).map(lambda v: re.sub(r"\s+", "", v)),
            "sp_main": df[cols["sp_main"]].map(normalize_species_code),
            "sp_admix": [()] * len(df)
            if not cols.get("sp_admix")
            else df[cols["sp_admix"]].map(
                lambda v: tuple(normalize_species_code(c) for c in re.split(r"[,;\s]+", v) if c)
                if isinstance(v, str) else ()
            ),
            "age": pd.array(pd.to_numeric(df[cols["age"]], errors="coerce"), dtype="Int64"),
            "hab": df[cols["hab"]].map(
                lambda v: normalize_habitat(None if pd.isna(v) else str(v))
            ),
            "fun": pd.Series(
                [_fun_value(v) for v in df[cols["fun"]]] if cols.get("fun")
                else [None] * len(df),
                index=df.index, dtype=object,
            ),
        },
        geometry=df.geometry.values,
        crs=4326,
    )
    out = out.drop_duplicates(subset="id").reset_index(drop=True)
    return out


def _get_json(session: requests.Session, url: str, params: dict) -> dict:
    last = None
    for attempt in range(RETRIES):
        try:
            r = session.get(url, params=params, timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as exc:
            last = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Pobieranie nie powiodło się: {url}: {last}")


def fetch_district(session, base_url: str, layer: str, prefix: str, flt: dict) -> list[dict]:
    cql = f"adr_for LIKE '{prefix}%'"
    if flt.get("column") and flt.get("values"):
        vals = ",".join(f"'{v}'" for v in flt["values"])
        cql += f" AND {flt['column']} IN ({vals})"
    url = f"{base_url}/collections/{layer}/items"
    features: list[dict] = []
    offset = 0
    while True:
        page = _get_json(session, url, {"f": "json", "limit": PAGE_LIMIT, "offset": offset,
                                        "filter": cql, "filter-lang": "cql-text"})
        got = page.get("features", [])
        features.extend(got)
        if len(got) < PAGE_LIMIT:
            return features
        offset += PAGE_LIMIT


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=RAW_DIR)
    ap.add_argument("--force", action="store_true", help="pobierz ponownie istniejące pliki")
    args = ap.parse_args(argv)

    cfg = yaml.safe_load(FIELDS_YAML.read_text(encoding="utf-8"))
    base_url = cfg.get("base_url", DEFAULT_BASE_URL)
    args.out.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    for d in cfg["districts"]:
        target = args.out / f"{d['prefix']}.geojson"
        if target.exists() and not args.force:
            print(f"{d['name']}: pomijam (jest {target.name})")
            continue
        feats = fetch_district(session, base_url, d["layer"], d["prefix"],
                               cfg.get("forest_filter") or {})
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps({"type": "FeatureCollection", "features": feats}),
                       encoding="utf-8")
        tmp.replace(target)
        print(f"{d['name']}: {len(feats)} wydzieleń")
    return 0


if __name__ == "__main__":
    sys.exit(main())
