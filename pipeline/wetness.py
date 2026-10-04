"""Wilgotność miejsca (spec L): bufor wodny wydzielenia -> wetness.parquet.

Składniki 0–1: bliskość wód i mokradeł, bliskość rowów/cieków, położenie w rzeźbie (TPI), siedlisko,
gleba, TWI. Surowa wartość = suma ważona; `wet` = percentyl surowej wartości w obszarze (0–100, mediana 50).
Parametry: sekcja `water:` w species.yaml.
"""
import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from forecast.species import ROOT, expand_habitat_list
from pipeline.habitat import ascii_code, normalize_habitat, soil_group

DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_OUT = DATA_DIR / "wetness.parquet"
COMPONENTS = ("water", "ditch", "valley", "habitat", "soil", "twi")
NEUTRAL = 0.5  # brak danych składnika (poza water/ditch, gdzie brak = brak wody w zasięgu = 0)
WL_HIGH = 65
WL_LOW = 35
HILLTOP = 0.25


@dataclass(frozen=True)
class WaterConfig:
    weights: dict
    water_dist: tuple[float, float]
    ditch_dist: tuple[float, float]
    habitat_default: float
    habitat_types: dict
    moist_codes: dict
    soil_groups: dict
    soil_gleyed: float


def load_config(path: Path = ROOT / "species.yaml") -> WaterConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    w = data["water"]
    sets = data.get("habitat_sets") or {}
    weights = {k: float(v) for k, v in w["weights"].items()}
    if set(weights) != set(COMPONENTS):
        raise ValueError(f"water.weights: oczekiwane składniki {COMPONENTS}, są {sorted(weights)}")
    types = {}
    for value, codes in w["habitat_types"]["values"].items():
        for code in expand_habitat_list(codes, sets, "water.habitat_types"):
            types.setdefault(code, float(value))  # pierwsza (najwyższa w pliku) wartość wygrywa
    return WaterConfig(
        weights=weights,
        water_dist=tuple(float(x) for x in w["water_dist"]),
        ditch_dist=tuple(float(x) for x in w["ditch_dist"]),
        habitat_default=float(w["habitat_types"]["default"]),
        habitat_types=types,
        moist_codes={str(k).upper(): float(v) for k, v in w["moist_codes"].items()},
        soil_groups={str(k).upper(): float(v) for k, v in w["soil_groups"].items()},
        soil_gleyed=float(w["soil_gleyed"]),
    )


def dist_value(d, full: float, zero: float) -> np.ndarray:
    """1.0 do `full` m, liniowo do 0 przy `zero` m; brak (nan) = dalej niż `zero` -> 0."""
    d = np.asarray(d, dtype=np.float64)
    v = np.clip((zero - d) / (zero - full), 0.0, 1.0)
    return np.where(np.isnan(d), 0.0, v)


def habitat_value(hab: str | None, moist: str | None, cfg: WaterConfig) -> float:
    """max(wartość typu siedliskowego, wartość kodu wilgotności); oba puste -> NEUTRAL."""
    vals = []
    if hab:
        vals.append(cfg.habitat_types.get(hab, cfg.habitat_default))
    if moist:
        m = cfg.moist_codes.get(moist)
        if m is not None:
            vals.append(m)
    return max(vals) if vals else NEUTRAL


def soil_value(code: str | None, cfg: WaterConfig) -> float:
    """Grupa gleby z tabeli; inaczej „g” w podtypie (oglejona) -> soil_gleyed; brak kodu -> NEUTRAL."""
    if not code:
        return NEUTRAL
    g = soil_group(code)
    if g in cfg.soil_groups:
        return cfg.soil_groups[g]
    rest = code.strip()[len(g or ""):]
    return cfg.soil_gleyed if "g" in rest else 0.0


def pct_rank(values) -> np.ndarray:
    """Percentyl 0–1 (średnia ranga przy remisach); nan zostaje nan."""
    s = pd.Series(values, dtype="float64")
    return s.rank(pct=True, method="average").to_numpy()


def reason(row: dict, wet: int, cfg: WaterConfig) -> str | None:
    """Kod powodu (spec L §1): przy wysokim wet największy wkład ważony, przy niskim hilltop/dry."""
    if wet >= WL_HIGH:
        return max(COMPONENTS, key=lambda c: cfg.weights[c] * row[c])
    if wet <= WL_LOW:
        return "hilltop" if row["valley"] < HILLTOP else "dry"
    return None


def combine(df: pd.DataFrame, cfg: WaterConfig) -> pd.DataFrame:
    """df z kolumnami d_water, d_ditch (m, nan = poza zasięgiem), tpi, twi, hab, moist, soil ->
    kolumny składników, raw, wet (int 0–100), wl."""
    out = pd.DataFrame(index=df.index)
    out["water"] = dist_value(df["d_water"], *cfg.water_dist)
    out["ditch"] = dist_value(df["d_ditch"], *cfg.ditch_dist)
    out["valley"] = np.nan_to_num(1.0 - pct_rank(df["tpi"]), nan=NEUTRAL)
    out["twi"] = np.nan_to_num(pct_rank(df["twi"]), nan=NEUTRAL)
    out["habitat"] = [habitat_value(h, m, cfg) for h, m in zip(df["hab"], df["moist"])]
    out["soil"] = [soil_value(s, cfg) for s in df["soil"]]
    out["raw"] = sum(cfg.weights[c] * out[c] for c in COMPONENTS)
    out["wet"] = np.rint(pct_rank(out["raw"]) * 100).astype(int)
    out["wl"] = [reason(r, w, cfg) for r, w in zip(out[list(COMPONENTS)].to_dict("records"), out["wet"])]
    return out


def nearest_dist(stands_2180: gpd.GeoDataFrame, feats_2180: gpd.GeoDataFrame, max_m: float) -> np.ndarray:
    """Odległość (m) od krawędzi wydzielenia do najbliższego obiektu; > max_m -> nan."""
    d = np.full(len(stands_2180), np.nan)
    if feats_2180.empty or stands_2180.empty:
        return d
    j = gpd.sjoin_nearest(stands_2180[["geometry"]].reset_index(drop=True), feats_2180[["geometry"]],
                          max_distance=max_m, distance_col="_d", how="inner")
    m = j.groupby(level=0)["_d"].min()
    d[m.index.to_numpy()] = m.to_numpy()
    return d


def _clean(v) -> str | None:
    return None if v is None or (not isinstance(v, str) and pd.isna(v)) or not str(v).strip() else str(v).strip()


def main(argv=None) -> int:
    from pipeline.ingest import DEFAULT_DB, DEFAULT_PARQUET, DEFAULT_TERRAIN, STANDS_SQL
    import duckdb

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--parquet", type=Path, default=DEFAULT_PARQUET)
    ap.add_argument("--terrain", type=Path, default=DEFAULT_TERRAIN)
    ap.add_argument("--water", type=Path, default=DATA_DIR / "woda.parquet")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    cfg = load_config()

    geo = gpd.read_parquet(args.parquet)[["prefix", "a_i_num", "geometry"]]
    geo = geo.drop_duplicates(["prefix", "a_i_num"]).reset_index(drop=True)
    con = duckdb.connect(str(args.db), read_only=True)
    try:
        attrs = con.execute(STANDS_SQL).df()[["prefix", "a_i_num", "hab", "moist", "soil"]]
    finally:
        con.close()
    attrs = attrs.drop_duplicates(["prefix", "a_i_num"])
    # ta sama populacja co load_stands (inner join): percentyle liczone wśród wydzieleń z opisem
    df = geo.merge(attrs, on=["prefix", "a_i_num"], how="inner").reset_index(drop=True)
    df["hab"] = [normalize_habitat(_clean(v)) for v in df["hab"]]
    df["moist"] = [None if _clean(v) is None else normalize_habitat(_clean(v)) for v in df["moist"]]
    df["soil"] = [None if _clean(v) is None else ascii_code(_clean(v)) for v in df["soil"]]
    if Path(args.terrain).exists():
        terr = pd.read_parquet(args.terrain)
        cols = [c for c in ("tpi", "twi") if c in terr.columns]
        df = df.merge(terr[["prefix", "a_i_num", *cols]].drop_duplicates(["prefix", "a_i_num"]),
                      on=["prefix", "a_i_num"], how="left")
    for c in ("tpi", "twi"):
        if c not in df.columns:
            print(f"Uwaga: brak {c} w terrain.parquet — składnik neutralny", file=sys.stderr)
            df[c] = np.nan

    st = gpd.GeoDataFrame(df, geometry="geometry", crs=geo.crs).to_crs(2180)
    water = gpd.read_parquet(args.water).to_crs(2180)
    print(f"wilgotność: {len(st)} wydzieleń, wód {int((water['kind'] == 'water').sum())}, "
          f"rowów/cieków {int((water['kind'] == 'ditch').sum())}", file=sys.stderr)
    df["d_water"] = nearest_dist(st, water[water["kind"] == "water"], cfg.water_dist[1])
    df["d_ditch"] = nearest_dist(st, water[water["kind"] == "ditch"], cfg.ditch_dist[1])
    res = combine(df, cfg)
    out = pd.concat([df[["prefix", "a_i_num", "d_water", "d_ditch"]], res], axis=1)
    table = pa.Table.from_pandas(out, preserve_index=False)
    meta = {**(table.schema.metadata or {}), b"weights": json.dumps(cfg.weights).encode()}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix(".tmp")
    pq.write_table(table.replace_schema_metadata(meta), tmp)
    tmp.replace(args.out)
    print(f"wilgotność: zapisano {args.out}; wl: {out['wl'].value_counts().to_dict()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
