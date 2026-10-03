"""Pobieranie parkingów przy lasach z OpenStreetMap (Overpass API)."""
import argparse
import json
import math
import sys
import time
from pathlib import Path

import geopandas as gpd
import requests
from shapely.geometry import Point, box

DATA_DIR = Path(__file__).resolve().parent / "data"
# Główny serwer i zapasowy (przy 429/504 kolejna próba idzie do następnego).
OVERPASS_URLS = ("https://overpass-api.de/api/interpreter",
                 "https://overpass.kumi.systems/api/interpreter")
OVERPASS_URL = OVERPASS_URLS[0]
TILE_DEG = 0.5
MAX_DIST_M = 300
DEFAULT_OUT = DATA_DIR / "parkingi.geojson"
DEFAULT_CACHE = DATA_DIR / "raw" / "osm"

_USER_AGENT = "gdzie-na-grzyby"
_RETRIES = 3
_BACKOFF_SECONDS = 30
_PAUSE_SECONDS = 5

MAX_SPLIT_DEPTH = 2  # kafel, którego serwer nie wyrabia, dzielimy na 4 (0,5° -> 0,25° -> 0,125°)


class OverpassError(RuntimeError):
    """Overpass nie odpowiedział poprawnie po wszystkich próbach."""


_ACCESS_REJECT = {"private", "no", "customers", "permit"}
_PARKING_REJECT = {"underground", "multi-storey", "rooftop"}


def tiles_for_bounds(bounds: tuple[float, float, float, float]) -> list[tuple[float, float, float, float]]:
    """Kafle 0,5° (south, west, north, east) pokrywające `bounds` = (west, south, east, north)."""
    west, south, east, north = bounds
    start_lat = math.floor(south / TILE_DEG) * TILE_DEG
    start_lon = math.floor(west / TILE_DEG) * TILE_DEG
    tiles = []
    lat = start_lat
    while lat < north:
        lon = start_lon
        while lon < east:
            tiles.append((lat, lon, lat + TILE_DEG, lon + TILE_DEG))
            lon += TILE_DEG
        lat += TILE_DEG
    return tiles


def query(bbox: tuple[float, float, float, float]) -> str:
    """Zapytanie Overpass QL dla kafla (south, west, north, east)."""
    south, west, north, east = bbox
    return (
        f'[out:json][timeout:90];\n'
        f'nwr["amenity"="parking"]({south},{west},{north},{east});\n'
        f'out center tags;'
    )


def fetch_tile(bbox, cache_dir, *, refresh=False, session=None, sleep=time.sleep) -> list[dict]:
    """Pobiera jeden kafel z Overpass lub wczytuje go z cache.

    Przy 429/504/timeoucie czeka 30 s i próbuje ponownie na kolejnym serwerze (maks. 3 próby);
    po pobraniu z sieci pauza 5 s (uprzejmość wobec Overpass), z cache bez pauzy.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    south, west, *_ = bbox
    north, east = bbox[2], bbox[3]
    cache_path = cache_dir / f"parking_{south:g}_{west:g}_{north - south:g}.json"

    if not refresh and cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8")).get("elements", [])

    sess = session or requests.Session()
    payload = {"data": query(bbox)}
    headers = {"User-Agent": _USER_AGENT}

    for attempt in range(_RETRIES):
        url = OVERPASS_URLS[attempt % len(OVERPASS_URLS)]
        try:
            r = sess.post(url, data=payload, headers=headers, timeout=120)
        except requests.Timeout:
            r = None
        if r is None or r.status_code in (429, 504):
            if attempt == _RETRIES - 1:
                break
            sleep(_BACKOFF_SECONDS)
            continue
        r.raise_for_status()
        data = r.json()
        cache_path.write_text(json.dumps(data), encoding="utf-8")
        sleep(_PAUSE_SECONDS)
        return data.get("elements", [])

    raise OverpassError(f"Overpass nie odpowiedział po {_RETRIES} próbach dla {bbox}")


def fetch_area(bbox, cache_dir, *, refresh=False, session=None, depth: int = 0) -> list[dict]:
    """fetch_tile, a gdy serwer nie wyrabia — rekurencyjnie cztery ćwiartki (do MAX_SPLIT_DEPTH)."""
    try:
        return fetch_tile(bbox, cache_dir, refresh=refresh, session=session)
    except OverpassError:
        if depth >= MAX_SPLIT_DEPTH:
            raise
    south, west, north, east = bbox
    mid_lat, mid_lon = (south + north) / 2, (west + east) / 2
    out: list[dict] = []
    for q in ((south, west, mid_lat, mid_lon), (south, mid_lon, mid_lat, east),
              (mid_lat, west, north, mid_lon), (mid_lat, mid_lon, north, east)):
        out.extend(fetch_area(q, cache_dir, refresh=refresh, session=session, depth=depth + 1))
    return out


def elements_to_gdf(elements: list[dict]) -> gpd.GeoDataFrame:
    """Elementy Overpass -> GeoDataFrame parkingów (punkty, CRS 4326)."""
    rows = []
    for el in elements:
        typ = el.get("type")
        eid = el.get("id")
        tags = el.get("tags") or {}

        if typ == "node":
            lat = el.get("lat")
            lon = el.get("lon")
        elif typ in ("way", "relation"):
            center = el.get("center")
            if not center:
                continue
            lat = center.get("lat")
            lon = center.get("lon")
        else:
            continue

        if lat is None or lon is None:
            continue
        if tags.get("access") in _ACCESS_REJECT:
            continue
        if tags.get("parking") in _PARKING_REJECT:
            continue

        fee = tags.get("fee")
        rows.append({
            "osm": f"{typ[0]}{eid}",
            "name": tags.get("name"),
            "fee": fee if fee in ("yes", "no") else None,
            "geometry": Point(lon, lat),
        })

    gdf = gpd.GeoDataFrame(rows, crs=4326)
    gdf = gdf.drop_duplicates(subset="osm").reset_index(drop=True)
    # Zachowaj None zamiast NaN w opcjonalnych kolumnach (GeoJSON zapisze null).
    if "fee" in gdf.columns:
        gdf["fee"] = gdf["fee"].astype(object).where(gdf["fee"].notna(), None)
    if "name" in gdf.columns:
        gdf["name"] = gdf["name"].astype(object).where(gdf["name"].notna(), None)
    return gdf


def near_forest(parkings: gpd.GeoDataFrame, stands: gpd.GeoDataFrame, max_dist_m: int = MAX_DIST_M) -> gpd.GeoDataFrame:
    """Zostawia parkingi w odległości ≤ `max_dist_m` od wydzieleń (EPSG:2180)."""
    if parkings.empty or stands.empty:
        return gpd.GeoDataFrame(columns=parkings.columns, crs=parkings.crs)

    park_2180 = parkings.to_crs(2180)
    stands_2180 = stands.to_crs(2180)
    joined = gpd.sjoin_nearest(
        park_2180, stands_2180[["geometry"]],
        max_distance=max_dist_m, how="inner",
    )
    return parkings.loc[joined.index.unique()].reset_index(drop=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--area", type=Path, default=DATA_DIR / "obszar.geojson")
    ap.add_argument("--parquet", type=Path, default=DATA_DIR / "stands.parquet")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args(argv)

    try:
        area = gpd.read_file(args.area).to_crs(4326)
        shape = area.union_all()
        tiles = [t for t in tiles_for_bounds(tuple(area.total_bounds))
                 if box(t[1], t[0], t[3], t[2]).intersects(shape)]
        stands = gpd.read_parquet(args.parquet)

        session = requests.Session()
        elements = []
        failed = 0
        for tile in tiles:
            try:
                elements.extend(fetch_area(tile, args.cache, refresh=args.refresh, session=session))
            except OverpassError as exc:  # częściowe dane są lepsze niż żadne; ponowny przebieg dociągnie
                failed += 1
                print(f"Uwaga: {exc}", file=sys.stderr)
        if failed:
            print(f"pominięto {failed} z {len(tiles)} kafli (Overpass); uruchom ponownie, by je dociągnąć",
                  file=sys.stderr)

        raw = elements_to_gdf(elements)
        print(f"parkingi: {len(raw)}")
        near = near_forest(raw, stands)
        print(f"parkingi po filtrze: {len(near)}")

        if near.empty:
            print("brak parkingów przy lasach", file=sys.stderr)
            return 0

        args.out.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.out.with_suffix(".tmp")
        near.to_file(tmp, driver="GeoJSON")
        tmp.replace(args.out)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
