"""Pobieranie rezerwatów przyrody z WFS GDOŚ i przycięcie do obszaru mapy."""
import argparse
import sys
from pathlib import Path

import geopandas as gpd
import requests
import shapely

from pipeline.fetch_bdl import _get_json

DATA_DIR = Path(__file__).resolve().parent / "data"
WFS_URL = "https://sdi.gdos.gov.pl/wfs"
TYPE_NAME = "GDOS:Rezerwaty"
RESERVES_PATH = DATA_DIR / "rezerwaty.geojson"
AREA_PATH = DATA_DIR / "obszar.geojson"


def wfs_params(bounds: tuple[float, float, float, float]) -> dict:
    """`bounds` = (minx, miny, maxx, maxy) w lon/lat; bbox WFS 2.0 dla EPSG:4326 to lat,lon."""
    minx, miny, maxx, maxy = bounds
    return {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": TYPE_NAME,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "bbox": f"{miny},{minx},{maxy},{maxx},urn:ogc:def:crs:EPSG::4326",
    }


def clip_reserves(fc: dict, area) -> gpd.GeoDataFrame:
    """Rezerwaty z FeatureCollection przycięte do `area`; kolumny name, geometry (EPSG:4326)."""
    features = fc.get("features") or []
    if not features:
        raise ValueError("WFS GDOŚ nie zwrócił żadnych rezerwatów")
    g = gpd.GeoDataFrame.from_features(features, crs=4326)
    g = g.rename(columns={"nazwa": "name"})[["name", "geometry"]]
    g["geometry"] = shapely.make_valid(g.geometry.values)
    g = gpd.clip(g, area, keep_geom_type=True)
    g = g[~g.geometry.is_empty & g.geometry.notna()].reset_index(drop=True)
    return g[["name", "geometry"]]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--area", type=Path, default=AREA_PATH)
    ap.add_argument("--out", type=Path, default=RESERVES_PATH)
    args = ap.parse_args(argv)
    try:
        area_gdf = gpd.read_file(args.area).to_crs(4326)
        area = area_gdf.union_all()
        fc = _get_json(requests.Session(), WFS_URL, wfs_params(tuple(area_gdf.total_bounds)))
        reserves = clip_reserves(fc, area)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.out.with_suffix(".tmp")
        reserves.to_file(tmp, driver="GeoJSON")
        tmp.replace(args.out)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 1
    print(f"rezerwaty: {len(reserves)} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
