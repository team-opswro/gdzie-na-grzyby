"""Build danych mapy: baza BDL (ingest) -> pipeline/data/out/.

Wynik: lasy.pmtiles, centroidy/index.json + centroidy/<lat0>_<lon0>.json, grid.json,
nazwy.json (kopia z fetch_names), gatunki.json (species_info), build.json.
Tippecanoe jest w kontenerze pipeline (README).
"""
import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import yaml

from forecast.species import load_species
from pipeline.build_tiles import (compute_features, mark_reserves, tippecanoe_cmd,
                                  write_centroid_tiles, write_geojsonseq, write_reserves_seq)
from pipeline.fetch_reserves import RESERVES_PATH
from pipeline.grid import build_grid
from pipeline.ingest import DATA_DIR, DEFAULT_DB, DEFAULT_PARQUET, load_stands
from pipeline.species_info import CONTENT_PATH, SPECIES_PATH, build_info

DEFAULT_OUT = DATA_DIR / "out"
DEFAULT_BUILD_DIR = DATA_DIR / "build"


def _write_json(path: Path, obj, **kw) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, **kw), encoding="utf-8")
    tmp.replace(path)


def run(stands: gpd.GeoDataFrame, species, reserves, out: Path, build_dir: Path,
        names_path: Path, tippecanoe=subprocess.run, now: str | None = None,
        build: str | None = None) -> dict:
    """Buduje wszystkie pliki w `out`; zwraca zawartość build.json."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    keys = list(species)

    feats = compute_features(stands, species)
    feats = mark_reserves(feats, reserves)
    with_partners = int(sum(1 for p in feats["partners"] if len(p))) \
        if "partners" in feats.columns else 0
    n_rez = int(feats["rez"].notna().sum())
    print(f"wydzielenia: {len(feats)}, z domieszkami: {with_partners}, w rezerwatach: {n_rez}")

    seq = Path(build_dir) / "lasy.geojsonseq"
    write_geojsonseq(feats, keys, seq)
    rseq = Path(build_dir) / "rezerwaty.geojsonseq"
    write_reserves_seq(reserves, rseq)
    tippecanoe(tippecanoe_cmd(out, {"lasy": seq, "rezerwaty": rseq}), check=True)

    index = write_centroid_tiles(feats, keys, out / "centroidy")
    n_centroids = sum(len(json.loads((out / "centroidy" / f"{t}.json").read_text())["rows"])
                      for t in index["tiles"])
    grid = build_grid(zip(feats["lat"], feats["lon"]))
    _write_json(out / "grid.json", grid, separators=(",", ":"))

    names_path = Path(names_path)
    if names_path.resolve() != (out / "nazwy.json").resolve():
        shutil.copyfile(names_path, out / "nazwy.json")
    info = build_info(yaml.safe_load(SPECIES_PATH.read_text(encoding="utf-8")),
                      yaml.safe_load(CONTENT_PATH.read_text(encoding="utf-8")))
    _write_json(out / "gatunki.json", info, indent=1)

    meta = {
        "build": build,
        "generated_at": now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "counts": {"stands": len(feats), "with_partners": with_partners, "rez": n_rez,
                   "centroids": n_centroids, "centroid_tiles": len(index["tiles"]),
                   "grid_cells": len(grid["cells"])},
    }
    _write_json(out / "build.json", meta, indent=1)
    print(f"centroidy: {n_centroids} w {len(index['tiles'])} kafelkach, "
          f"komorki siatki: {len(grid['cells'])}")
    return meta


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--parquet", type=Path, default=DEFAULT_PARQUET)
    ap.add_argument("--reserves", type=Path, default=RESERVES_PATH)
    ap.add_argument("--names", type=Path, default=DEFAULT_OUT / "nazwy.json",
                    help="nazwy.json z fetch_names (kopiowany do --out)")
    ap.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD_DIR)
    args = ap.parse_args(argv)
    if not args.reserves.exists():
        print(f"brak pliku rezerwatów {args.reserves}: uruchom python -m pipeline.fetch_reserves",
              file=sys.stderr)
        return 1
    if not args.names.exists():
        print(f"brak pliku nazw {args.names}: uruchom python -m pipeline.fetch_names",
              file=sys.stderr)
        return 1

    stands = load_stands(args.db, args.parquet)
    reserves = gpd.read_file(args.reserves).to_crs(4326)
    run(stands, load_species(), reserves, args.out, args.build_dir, args.names,
        tippecanoe=subprocess.run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
