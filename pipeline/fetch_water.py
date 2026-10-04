"""Wody z OpenStreetMap dla wskaźnika wilgotności miejsca (spec L).

Źródło: wycinki województw z Geofabrik (`*.osm.pbf`, czytane lokalnie przez GDAL) — Overpass nie wyrabia
zapytań o rowy i cieki dla całego obszaru. Pobierane są tylko województwa, których granica (`*.poly`)
przecina obszar.

Wynik: pipeline/data/woda.parquet — kolumny `kind` (`water`: wody stojące ≥ 0,5 ha, rzeki, mokradła;
`ditch`: rowy, strumienie, kanały) i geometria (EPSG:4326).
"""
import argparse
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
import requests
from shapely.geometry import Polygon

DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_OUT = DATA_DIR / "woda.parquet"
DEFAULT_CACHE = DATA_DIR / "raw" / "osm" / "pbf"
GEOFABRIK = "https://download.geofabrik.de/europe/poland/"
REGIONS = ("dolnoslaskie", "kujawsko-pomorskie", "lodzkie", "lubelskie", "lubuskie", "malopolskie",
           "mazowieckie", "opolskie", "podkarpackie", "podlaskie", "pomorskie", "slaskie",
           "swietokrzyskie", "warminsko-mazurskie", "wielkopolskie", "zachodniopomorskie")
MIN_WATER_M2 = 5000  # wody stojące mniejsze niż 0,5 ha pomijane (oczka, baseny)
RIVER = ("river",)
DITCH = ("stream", "ditch", "drain", "canal")
AREA_NATURAL = ("water", "wetland")


def parse_poly(text: str) -> Polygon | None:
    """Format Osmosis .poly -> (multi)poligon zewnętrznych pierścieni (dziury pomijane)."""
    rings, cur, name = [], None, None
    for line in text.splitlines()[1:]:
        s = line.strip()
        if not s:
            continue
        if cur is None:
            if s == "END":
                break
            name, cur = s, []
        elif s == "END":
            if len(cur) >= 3 and not name.startswith("!"):
                rings.append(Polygon(cur))
            cur = None
        else:
            x, y = s.split()[:2]
            cur.append((float(x), float(y)))
    if not rings:
        return None
    return gpd.GeoSeries(rings).union_all()


def _get(url: str, session) -> requests.Response:
    r = session.get(url, stream=True, timeout=300)
    r.raise_for_status()
    return r


def regions_for(area_shape, cache_dir: Path, session) -> list[str]:
    """Województwa, których granica Geofabrik przecina obszar (pliki .poly w cache)."""
    out = []
    for name in REGIONS:
        path = cache_dir / f"{name}.poly"
        if not path.exists():
            path.write_text(_get(GEOFABRIK + f"{name}.poly", session).text, encoding="utf-8")
        poly = parse_poly(path.read_text(encoding="utf-8"))
        if poly is not None and poly.intersects(area_shape):
            out.append(name)
    return out


def download_pbf(name: str, cache_dir: Path, session, refresh: bool = False) -> Path:
    path = cache_dir / f"{name}-latest.osm.pbf"
    if path.exists() and not refresh:
        return path
    part = path.with_suffix(".part")
    with _get(GEOFABRIK + f"{name}-latest.osm.pbf", session) as r, part.open("wb") as fh:
        for chunk in r.iter_content(1 << 20):
            fh.write(chunk)
    part.replace(path)
    return path


def _in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


def read_pbf(path: Path, bbox) -> gpd.GeoDataFrame:
    """Linie (rzeki, rowy, cieki) i poligony (wody, mokradła) z jednego PBF, przycięte do bbox."""
    lines = pyogrio.read_dataframe(path, layer="lines", bbox=bbox, columns=["waterway"],
                                   where=f"waterway IN ({_in(RIVER + DITCH)})")
    polys = pyogrio.read_dataframe(path, layer="multipolygons", bbox=bbox, columns=["natural"],
                                   where=f"natural IN ({_in(AREA_NATURAL)})")
    lines["kind"] = ["water" if w in RIVER else "ditch" for w in lines["waterway"]]
    polys["kind"] = "water"
    out = pd.concat([lines[["kind", "geometry"]], polys[["kind", "geometry"]]], ignore_index=True)
    return gpd.GeoDataFrame(out, geometry="geometry", crs=4326)


def drop_small_water(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.empty:
        return gdf
    is_poly = gdf.geom_type.isin(["Polygon", "MultiPolygon"])
    small = is_poly & (gdf.to_crs(2180).area < MIN_WATER_M2)
    return gdf[~small].reset_index(drop=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--area", type=Path, default=DATA_DIR / "obszar.geojson")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--refresh", action="store_true", help="pobierz PBF ponownie")
    args = ap.parse_args(argv)

    area = gpd.read_file(args.area).to_crs(4326)
    shape = area.union_all()
    # zapas ~2 km: woda tuż za granicą obszaru też nawilża wydzielenia przy granicy
    bbox = tuple(area.total_bounds + [-0.03, -0.02, 0.03, 0.02])
    args.cache.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = "gdzie-na-grzyby"
    try:
        names = regions_for(shape.buffer(0.03), args.cache, session)
        parts = []
        for name in names:
            print(f"woda: {name}", file=sys.stderr)
            parts.append(read_pbf(download_pbf(name, args.cache, session, args.refresh), bbox))
    except (OSError, requests.RequestException) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 1
    gdf = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=4326)
    # obiekty na granicy województw są w obu wycinkach
    gdf = gdf[~gdf.geometry.to_wkb().duplicated()]
    gdf = drop_small_water(gdf)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix(".tmp")
    gdf.to_parquet(tmp)
    tmp.replace(args.out)
    print(f"woda: {len(gdf)} obiektów {gdf['kind'].value_counts().to_dict()} -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
