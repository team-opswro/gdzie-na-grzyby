"""Obszar mapy = granica woj. opolskiego + całe nadleśnictwa spoza woj. (`whole: true`)."""
import argparse
import sys
from pathlib import Path

import geopandas as gpd
import requests
import shapely
import yaml
from shapely.geometry import shape

from pipeline.fetch_bdl import DEFAULT_BASE_URL, FIELDS_YAML, _get_json

DATA_DIR = Path(__file__).resolve().parent / "data"
SIMPLIFY_M = 100


def build_area(base, extra):
    """Suma granicy bazowej (GeoDataFrame lub geometria) i obrysów `extra` (lista geometrii)."""
    base_geom = base.union_all() if hasattr(base, "union_all") else base
    geoms = [base_geom, *extra]
    return shapely.make_valid(shapely.union_all(geoms))


def fetch_outline(session, base_url: str, prefix: str):
    region, insp = prefix.split("-")
    page = _get_json(session, f"{base_url}/collections/nadlesnictwa/items", {
        "f": "json", "limit": 10, "filter-lang": "cql-text",
        "filter": f"region_cd='{region}' AND inspectorate_cd='{insp}'"})
    feats = page.get("features", [])
    if len(feats) != 1:
        raise RuntimeError(f"nadlesnictwa {prefix}: oczekiwano 1 obiektu, jest {len(feats)}")
    return shape(feats[0]["geometry"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", type=Path, default=DATA_DIR / "opolskie.geojson")
    ap.add_argument("--out", type=Path, default=DATA_DIR / "obszar.geojson")
    args = ap.parse_args(argv)

    cfg = yaml.safe_load(FIELDS_YAML.read_text(encoding="utf-8"))
    base_url = cfg.get("base_url", DEFAULT_BASE_URL)
    session = requests.Session()
    extra = []
    for d in cfg["districts"]:
        if d.get("whole"):
            extra.append(fetch_outline(session, base_url, d["prefix"]))
            print(f"{d['name']}: obrys pobrany")
    base = gpd.read_file(args.base).to_crs(4326)
    area = build_area(base, extra)
    simple = gpd.GeoSeries([area], crs=4326).to_crs(2180).simplify(SIMPLIFY_M).to_crs(4326)
    out = gpd.GeoDataFrame({"name": ["obszar"]}, geometry=simple, crs=4326)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_file(args.out, driver="GeoJSON")
    print(f"zapisano {args.out} ({args.out.stat().st_size} B)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
