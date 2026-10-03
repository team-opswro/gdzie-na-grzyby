"""BDL -> lasy.pmtiles + centroidy.json + grid.json."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely
import yaml

from forecast.species import Species, load_species
from pipeline.fetch_bdl import FIELDS_YAML, load_bdl
from pipeline.fetch_reserves import RESERVES_PATH
from pipeline.grid import build_grid, cell_id
from pipeline.habitat import Stand, habitat_score

ROOT = Path(__file__).resolve().parent.parent
CENTROID_THRESHOLD = 40
MINZOOM, MAXZOOM = 8, 14
ATTRS = ["id", "cell", "sp", "age", "hab"]


def compute_features(gdf: gpd.GeoDataFrame, species: dict[str, Species], boundary=None):
    """Przycina do `boundary`, dodaje lat/lon/cell (z representative_point) i h_<klucz> (0-100)."""
    gdf = gdf.copy()
    gdf["geometry"] = shapely.make_valid(gdf.geometry.values)
    if boundary is not None:
        if hasattr(boundary, "union_all"):
            boundary = boundary.union_all()
        gdf = gpd.clip(gdf, boundary, keep_geom_type=True).sort_index()
    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()].reset_index(drop=True)

    pts = gdf.geometry.representative_point()
    gdf["lat"] = pts.y.values
    gdf["lon"] = pts.x.values
    gdf["cell"] = [cell_id(la, lo) for la, lo in zip(gdf["lat"], gdf["lon"])]

    cache: dict[tuple, dict[str, int]] = {}
    keys = list(species)
    rows = []
    for sp, adm, age, hab in zip(gdf["sp_main"], gdf["sp_admix"], gdf["age"], gdf["hab"]):
        key = (sp, tuple(adm), None if age is None or age != age else int(age), hab)
        if key not in cache:
            st = Stand(*key)
            cache[key] = {k: int(round(100 * habitat_score(st, species[k]))) for k in keys}
        rows.append(cache[key])
    for k in keys:
        gdf[f"h_{k}"] = [r[k] for r in rows]
    return gdf


def mark_reserves(feats: gpd.GeoDataFrame, reserves) -> gpd.GeoDataFrame:
    """Kopia z kolumną `rez`: nazwa rezerwatu (punkt reprezentatywny w poligonie GDOŚ),
    "rezerwat" (forest_fun zaczyna się od REZ) albo None."""
    out = feats.copy()
    rez = pd.Series([None] * len(out), index=out.index, dtype=object)
    if reserves is not None and len(reserves) and len(out):
        pts = gpd.GeoDataFrame({"_i": range(len(out))},
                               geometry=gpd.points_from_xy(out["lon"], out["lat"]), crs=4326)
        res = reserves[["name", "geometry"]].to_crs(4326).reset_index(drop=True)
        res["_r"] = range(len(res))
        j = gpd.sjoin(pts, res, predicate="within", how="inner")
        j = j.sort_values(["_i", "_r"]).drop_duplicates("_i")
        for i, name in zip(j["_i"], j["name"]):
            rez.iloc[i] = name if isinstance(name, str) and name.strip() else "rezerwat"
    if "fun" in out.columns:
        flag = out["fun"].map(lambda v: isinstance(v, str) and v.startswith("REZ"))
        rez = rez.where(rez.notna() | ~flag, "rezerwat")
    out["rez"] = rez.astype(object)
    return out


def write_reserves_seq(reserves: gpd.GeoDataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for name, geom in zip(reserves["name"], reserves.geometry):
            props = {"name": name} if isinstance(name, str) and name.strip() else {}
            fh.write(json.dumps({"type": "Feature", "properties": props,
                                 "geometry": json.loads(shapely.to_geojson(geom))},
                                ensure_ascii=False) + "\n")


def tippecanoe_cmd(out: Path, layers: dict[str, Path]) -> list[str]:
    cmd = ["tippecanoe", "-o", str(out / "lasy.pmtiles")]
    for name, seq in layers.items():
        cmd += ["-L", f"{name}:{seq}"]
    return cmd + [f"-Z{MINZOOM}", f"-z{MAXZOOM}", "--drop-smallest-as-needed", "--force"]


def write_centroids(gdf, keys: list[str], path: Path, threshold: int = CENTROID_THRESHOLD) -> int:
    cols = [f"h_{k}" for k in keys]
    sel = gdf[gdf[cols].max(axis=1) >= threshold]
    if "rez" in sel.columns:
        sel = sel[sel["rez"].isna()]
    rows = [
        [i, round(float(la), 5), round(float(lo), 5), c, *[int(v) for v in hs]]
        for i, la, lo, c, hs in zip(sel["id"], sel["lat"], sel["lon"], sel["cell"],
                                    sel[cols].to_numpy())
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"species": keys, "rows": rows}, separators=(",", ":")),
                    encoding="utf-8")
    return len(rows)


def write_geojsonseq(gdf, keys: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    hcols = [f"h_{k}" for k in keys]
    with path.open("w", encoding="utf-8") as fh:
        for rec, geom in zip(gdf.itertuples(index=False), gdf.geometry):
            props = {"id": rec.id, "cell": rec.cell, "sp": rec.sp_main,
                     "age": None if rec.age is None or rec.age != rec.age else int(rec.age),
                     "hab": rec.hab}
            for c in hcols:
                props[c] = int(getattr(rec, c))
            rez = getattr(rec, "rez", None)
            if isinstance(rez, str) and rez:
                props["rez"] = rez
            props = {k: v for k, v in props.items() if v is not None}
            fh.write(json.dumps({"type": "Feature", "properties": props,
                                 "geometry": json.loads(shapely.to_geojson(geom))},
                                ensure_ascii=False) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bdl", type=Path, required=True)
    ap.add_argument("--boundary", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--build-dir", type=Path, default=ROOT / "pipeline" / "data" / "build")
    ap.add_argument("--reserves", type=Path, default=RESERVES_PATH)
    args = ap.parse_args(argv)
    if not args.reserves.exists():
        print(f"brak pliku rezerwatów {args.reserves}: uruchom python -m pipeline.fetch_reserves",
              file=sys.stderr)
        return 1

    cfg = yaml.safe_load(FIELDS_YAML.read_text(encoding="utf-8"))
    species = load_species()
    keys = list(species)

    gdf = load_bdl(args.bdl, cfg)
    print(f"po filtrze lasu: {len(gdf)}")
    boundary = gpd.read_file(args.boundary).to_crs(4326)
    feats = compute_features(gdf, species, boundary)
    print(f"po przycieciu: {len(feats)}")
    reserves = gpd.read_file(args.reserves).to_crs(4326)
    feats = mark_reserves(feats, reserves)
    print(f"wydzielenia w rezerwatach: {int(feats['rez'].notna().sum())}")

    args.out.mkdir(parents=True, exist_ok=True)
    seq = args.build_dir / "lasy.geojsonseq"
    write_geojsonseq(feats, keys, seq)
    rseq = args.build_dir / "rezerwaty.geojsonseq"
    write_reserves_seq(reserves, rseq)
    subprocess.run(tippecanoe_cmd(args.out, {"lasy": seq, "rezerwaty": rseq}), check=True)

    n = write_centroids(feats, keys, args.out / "centroidy.json")
    grid = build_grid(zip(feats["lat"], feats["lon"]))
    (args.out / "grid.json").write_text(json.dumps(grid, separators=(",", ":")),
                                        encoding="utf-8")
    print(f"centroidy: {n}, komorki siatki: {len(grid['cells'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
