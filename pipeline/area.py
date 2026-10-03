"""Obszar mapy = suma obrysów wszystkich nadleśnictw (paczki: G_INSPECTORATE; API: kolekcja
`nadlesnictwa`), uproszczona do 100 m w EPSG:2180 -> pipeline/data/obszar.geojson."""
import argparse
import sys
from pathlib import Path

import geopandas as gpd
import requests
import shapely
import yaml
from shapely.geometry import shape

from pipeline.fetch_bdl import DEFAULT_BASE_URL, FIELDS_YAML, _get_json
from pipeline.ingest import DEFAULT_DB, DEFAULT_OUTLINE

DATA_DIR = Path(__file__).resolve().parent / "data"
SIMPLIFY_M = 100


def build_area_from_outlines(outlines):
    """Suma obrysów (GeoDataFrame lub lista geometrii); bez przycinania do województwa."""
    geoms = list(outlines.geometry) if hasattr(outlines, "geometry") else list(outlines)
    if not geoms:
        raise ValueError("brak obrysów nadleśnictw")
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
    ap.add_argument("--outlines", type=Path, default=DEFAULT_OUTLINE,
                    help="obrysy z pipeline.ingest (prefix, name)")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--out", type=Path, default=DATA_DIR / "obszar.geojson")
    args = ap.parse_args(argv)

    cfg = yaml.safe_load(FIELDS_YAML.read_text(encoding="utf-8")) or {}
    base_url = cfg.get("base_url", DEFAULT_BASE_URL)
    if not args.outlines.exists():
        print(f"brak {args.outlines}: uruchom python -m pipeline.ingest", file=sys.stderr)
        return 1
    outlines = gpd.read_file(args.outlines).to_crs(4326)
    have = set(outlines["prefix"])
    geoms = list(outlines.geometry)
    session = requests.Session()
    for d in cfg.get("api_districts") or []:
        if d["prefix"] in have:
            continue  # paczka wygrywa z API
        geoms.append(fetch_outline(session, base_url, d["prefix"]))
        have.add(d["prefix"])
        print(f"{d['name']}: obrys pobrany z API")
    area = build_area_from_outlines(geoms)
    simple = gpd.GeoSeries([area], crs=4326).to_crs(2180).simplify(SIMPLIFY_M)
    km2 = simple.area.iloc[0] / 1e6
    out = gpd.GeoDataFrame({"name": ["obszar"]}, geometry=simple.to_crs(4326), crs=4326)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_file(args.out, driver="GeoJSON")
    print(f"nadleśnictw: {len(have)}, powierzchnia: {km2:.0f} km2")
    print(f"zapisano {args.out} ({args.out.stat().st_size} B)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
