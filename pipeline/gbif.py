"""Obserwacje grzybów z GBIF do walidacji modelu (spec H §2): gatunki + tło „wszystkie grzyby”."""
import json
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests
from shapely.geometry import Point

GBIF_API = "https://api.gbif.org/v1"
PAGE = 300
MAX_RECORDS = 100_000
MAX_UNCERTAINTY_M = 100
FUNGI_KINGDOM_KEY = 5
TIMEOUT_S = 30
RETRIES = 3
PAGE_PAUSE_S = 0.2
COLUMNS = ["species", "gbif_id", "lat", "lon", "date"]


class GbifError(Exception):
    pass


def _get(url: str, params: dict, session, sleep) -> dict:
    http = session or requests
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            r = http.get(url, params=params, timeout=TIMEOUT_S)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            last = e
            if attempt < RETRIES - 1:
                sleep(2 ** attempt)
    raise GbifError(f"GBIF niedostępny po {RETRIES} próbach: {last!r}")


def match_taxon(latin: str, *, session=None, sleep=time.sleep) -> int | None:
    """usageKey gatunku dla nazwy łacińskiej; None, gdy brak dopasowania na poziomie gatunku."""
    d = _get(GBIF_API + "/species/match", {"name": latin, "kingdom": "Fungi"}, session, sleep)
    if d.get("matchType") in ("EXACT", "FUZZY") and d.get("rank") == "SPECIES":
        return d.get("usageKey")
    return None


def area_wkt(area) -> str:
    """Prostokąt otaczający, wierzchołki przeciwnie do ruchu wskazówek (wymóg GBIF), „lon lat”."""
    minx, miny, maxx, maxy = area.bounds
    pts = [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy), (minx, miny)]
    return "POLYGON((" + ", ".join(f"{x} {y}" for x, y in pts) + "))"


def base_query(area, year_to: int) -> dict:
    return {
        "geometry": area_wkt(area),
        "hasCoordinate": "true",
        "hasGeospatialIssue": "false",
        "basisOfRecord": "HUMAN_OBSERVATION",
        "occurrenceStatus": "PRESENT",
        "year": f"2000,{year_to}",
        "limit": PAGE,
    }


def fetch_records(query: dict, cache_dir: Path, *, refresh: bool = False, session=None,
                  sleep=time.sleep) -> list[dict]:
    """Wszystkie rekordy zapytania; strony w cache_dir/<offset>.json (wznawialne)."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out: list[dict] = []
    offset = 0
    while offset < MAX_RECORDS:
        path = cache_dir / f"{offset}.json"
        if path.exists() and not refresh:
            page = json.loads(path.read_text(encoding="utf-8"))
        else:
            page = _get(GBIF_API + "/occurrence/search", {**query, "offset": offset}, session, sleep)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(page, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
            sleep(PAGE_PAUSE_S)
        out.extend(page.get("results") or [])
        if page.get("endOfRecords", True):
            break
        offset += PAGE
    return out


def parse_day(rec: dict) -> date | None:
    """Dzień obserwacji; None dla zakresu dat lub braku dnia."""
    if "/" in str(rec.get("eventDate") or ""):
        return None
    try:
        return date(int(rec["year"]), int(rec["month"]), int(rec["day"]))
    except (KeyError, TypeError, ValueError):
        return None


def clean(records: list[dict], area, label: str) -> pd.DataFrame:
    rows = []
    seen = set()
    for rec in records:
        key = rec.get("key")
        unc = rec.get("coordinateUncertaintyInMeters")
        lat, lon = rec.get("decimalLatitude"), rec.get("decimalLongitude")
        if key in seen or unc is None or unc > MAX_UNCERTAINTY_M or lat is None or lon is None:
            continue
        day = parse_day(rec)
        if day is None or not area.contains(Point(lon, lat)):
            continue
        seen.add(key)
        rows.append((label, key, float(lat), float(lon), day))
    return pd.DataFrame(rows, columns=COLUMNS)


def load_observations(latin_by_key: dict[str, str], area, cache_root: Path, *, refresh: bool = False,
                      session=None, sleep=time.sleep, year_to: int
                      ) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """(obecności gatunków, tło wszystkich grzybów z species="*", ostrzeżenia)."""
    cache_root = Path(cache_root)
    q = base_query(area, year_to)
    warnings: list[str] = []
    parts = []
    for key, latin in latin_by_key.items():
        taxon = match_taxon(latin, session=session, sleep=sleep)
        if taxon is None:
            warnings.append(f"{key}: brak dopasowania GBIF dla „{latin}” — pominięty")
            continue
        print(f"GBIF: {key} ({latin}, taxonKey={taxon})", file=sys.stderr)
        recs = fetch_records({**q, "taxonKey": taxon}, cache_root / key, refresh=refresh,
                             session=session, sleep=sleep)
        parts.append(clean(recs, area, key))
    print("GBIF: tło (wszystkie grzyby)", file=sys.stderr)
    bg_recs = fetch_records({**q, "kingdomKey": FUNGI_KINGDOM_KEY}, cache_root / "fungi",
                            refresh=refresh, session=session, sleep=sleep)
    presences = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=COLUMNS)
    return presences, clean(bg_recs, area, "*"), warnings
