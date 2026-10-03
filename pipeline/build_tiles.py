"""Funkcje budowy danych mapy: h_*, rezerwaty, GeoJSONSeq dla tippecanoe, centroidy w kafelkach.

Orkiestracja: `python -m pipeline.build`.
"""
import json
import math
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely

from forecast.species import Species
from pipeline.grid import cell_id
from pipeline.habitat import Stand, habitat_score

CENTROID_THRESHOLD = 40
CENTROID_TILE = 0.5
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

    def _age(a):
        return None if a is None or pd.isna(a) else int(a)

    cache: dict[tuple, dict[str, int]] = {}
    keys = list(species)
    rows = []
    parts = gdf["partners"] if "partners" in gdf.columns else [()] * len(gdf)
    for sp, adm, age, hab, pt in zip(gdf["sp_main"], gdf["sp_admix"], gdf["age"], gdf["hab"], parts):
        key = (sp, tuple(adm), _age(age), hab, tuple((c, s_, _age(a)) for c, s_, a in pt))
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


def write_parkings_seq(gdf: gpd.GeoDataFrame, path: Path) -> None:
    """GeoJSONSeq parkingów z `tippecanoe: {minzoom: 11}`; atrybuty: osm, opcjonalnie name/fee."""
    path.parent.mkdir(parents=True, exist_ok=True)
    names = gdf["name"] if "name" in gdf.columns else [None] * len(gdf)
    fees = gdf["fee"] if "fee" in gdf.columns else [None] * len(gdf)
    with path.open("w", encoding="utf-8") as fh:
        for osm, name, fee, geom in zip(gdf["osm"], names, fees, gdf.geometry):
            props = {"osm": osm}
            if isinstance(name, str) and name.strip():
                props["name"] = name
            if fee in ("yes", "no"):
                props["fee"] = fee
            fh.write(json.dumps({"type": "Feature", "tippecanoe": {"minzoom": 11},
                                 "properties": props,
                                 "geometry": json.loads(shapely.to_geojson(geom))},
                                ensure_ascii=False) + "\n")


def tippecanoe_cmd(out: Path, layers: dict[str, Path]) -> list[str]:
    cmd = ["tippecanoe", "-o", str(out / "lasy.pmtiles")]
    for name, seq in layers.items():
        cmd += ["-L", f"{name}:{seq}"]
    return cmd + [f"-Z{MINZOOM}", f"-z{MAXZOOM}", "--drop-smallest-as-needed", "--force"]


def tile_key(lat: float, lon: float) -> str:
    """Klucz kafelka centroidów 0,5°: "<lat0>_<lon0>", lat0 = floor(lat/0.5)*0.5 ("%.1f")."""
    def lo(v):
        return math.floor(round(v / CENTROID_TILE, 9)) * CENTROID_TILE + 0.0
    return f"{lo(lat):.1f}_{lo(lon):.1f}"


def centroid_rows(gdf, keys: list[str], threshold: int = CENTROID_THRESHOLD) -> list[list]:
    """Wiersze [id, lat, lon, cell, h_...] wydzieleń z max h >= threshold, bez rezerwatów."""
    cols = [f"h_{k}" for k in keys]
    sel = gdf[gdf[cols].max(axis=1) >= threshold]
    if "rez" in sel.columns:
        sel = sel[sel["rez"].isna()]
    return [
        [i, round(float(la), 5), round(float(lo), 5), c, *[int(v) for v in hs]]
        for i, la, lo, c, hs in zip(sel["id"], sel["lat"], sel["lon"], sel["cell"],
                                    sel[cols].to_numpy())
    ]


def write_centroid_tiles(gdf, keys: list[str], out_dir: Path,
                         threshold: int = CENTROID_THRESHOLD) -> dict:
    """Zapisuje `out_dir/index.json` i `out_dir/<lat0>_<lon0>.json` ({rows}); zwraca index.
    Stare pliki *.json w `out_dir` są usuwane."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.json"):
        old.unlink()
    tiles: dict[str, list] = {}
    for row in centroid_rows(gdf, keys, threshold):
        tiles.setdefault(tile_key(row[1], row[2]), []).append(row)
    for key, rows in tiles.items():
        (out_dir / f"{key}.json").write_text(json.dumps({"rows": rows}, separators=(",", ":")),
                                             encoding="utf-8")
    index = {"tile": CENTROID_TILE, "species": list(keys), "tiles": sorted(tiles)}
    (out_dir / "index.json").write_text(json.dumps(index, separators=(",", ":")),
                                        encoding="utf-8")
    return index


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
