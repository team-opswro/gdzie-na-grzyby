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
FIRST_YEAR = 2000
# GBIF oddaje głębokie strony (offset rzędu 10 000) bardzo wolno — duże zbiory dzielimy na
# lata, a lata powyżej SPLIT_COUNT rekordów na miesiące, żeby offsety zostały małe.
SPLIT_COUNT = 3000
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
        "year": f"{FIRST_YEAR},{year_to}",
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


def fetch_split(query: dict, cache_dir: Path, year_to: int, *, refresh: bool = False, session=None,
                sleep=time.sleep) -> list[dict]:
    """Jak fetch_records, ale rok po roku (a lata ponad SPLIT_COUNT — miesiąc po miesiącu)."""
    out: list[dict] = []
    kw = {"refresh": refresh, "session": session, "sleep": sleep}
    for year in range(FIRST_YEAR, year_to + 1):
        q = {**query, "year": str(year)}
        ydir = Path(cache_dir) / str(year)
        recs = _first_page_or_all(q, ydir, **kw)
        if recs is not None:
            out.extend(recs)
            continue
        for month in range(1, 13):
            out.extend(fetch_records({**q, "month": str(month)},
                                     Path(cache_dir) / f"{year}-{month:02d}", **kw))
    return out


def _first_page_or_all(q: dict, ydir: Path, **kw) -> list[dict] | None:
    """Wszystkie rekordy roku albo None, gdy pierwsza strona (cache: ydir/0.json) zgłasza
    więcej niż SPLIT_COUNT rekordów (wtedy pobieramy miesiącami)."""
    first = ydir / "0.json"
    if not first.exists() or kw["refresh"]:
        page = _get(GBIF_API + "/occurrence/search", {**q, "offset": 0}, kw["session"], kw["sleep"])
        ydir.mkdir(parents=True, exist_ok=True)
        first.write_text(json.dumps(page, ensure_ascii=False), encoding="utf-8")
    page = json.loads(first.read_text(encoding="utf-8"))
    if (page.get("count") or 0) > SPLIT_COUNT:
        return None
    return fetch_records(q, ydir, refresh=False, session=kw["session"], sleep=kw["sleep"])


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
    bg_recs = fetch_split({**q, "kingdomKey": FUNGI_KINGDOM_KEY}, cache_root / "fungi", year_to,
                          refresh=refresh, session=session, sleep=sleep)
    presences = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=COLUMNS)
    return presences, clean(bg_recs, area, "*"), warnings
