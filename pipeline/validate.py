"""Walidacja modelu na obserwacjach GBIF (spec H): AUC/lift siedliska i AUC pogody per gatunek.

Raport offline: pipeline/data/walidacja/ (nie out/ — publish wysyła cały katalog builda).
"""
import dataclasses
import random
from collections import defaultdict
from datetime import date, timedelta
from typing import Callable, Sequence

import geopandas as gpd
import pandas as pd

from forecast.model import DailySeries, WeatherComponents, weather_multiplier
from forecast.species import Species
from pipeline.grid import cell_id
from pipeline.habitat import HABITAT_FACTORS, habitat_components, habitat_score, stand_from_row
from pipeline.meteo_hist import HIST_START

MIN_PRESENCES = 30
BG_RATIO = 20
LIFT_H = 0.6
SEED = 0
TOO_FEW = "za mało danych"
WX_BG_PER_PRESENCE = 5
SEASON_MARGIN_DAYS = 14
WX_COMPONENTS = [f.name for f in dataclasses.fields(WeatherComponents) if f.name != "w"]


def auc(pos: Sequence[float], neg: Sequence[float]) -> float | None:
    """AUC (Mann–Whitney): P(pos > neg) + ½·P(remis); None, gdy któraś lista pusta."""
    if not len(pos) or not len(neg):
        return None
    ranked = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    rank_sum = 0.0
    i = 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and ranked[j][0] == ranked[i][0]:
            j += 1
        mid = (i + 1 + j) / 2  # średnia ranga grupy remisów (rangi od 1)
        rank_sum += mid * sum(1 for k in range(i, j) if ranked[k][1])
        i = j
    n_pos, n_neg = len(pos), len(neg)
    return (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def rng_for(key: str) -> random.Random:
    """RNG per gatunek: wynik gatunku nie zależy od tego, które inne gatunki liczono."""
    return random.Random(f"{SEED}:{key}")


def join_stands(obs: pd.DataFrame, stands: gpd.GeoDataFrame) -> tuple[pd.DataFrame, int]:
    """Obserwacje z kolumną `stand` (indeks wiersza stands); jedno trafienie na gbif_id."""
    pts = gpd.GeoDataFrame(obs.reset_index(drop=True),
                           geometry=gpd.points_from_xy(obs["lon"], obs["lat"]), crs=4326)
    st = stands[["geometry"]].to_crs(4326).reset_index(drop=True)
    st["stand"] = range(len(st))
    j = gpd.sjoin(pts, st, predicate="within", how="inner")
    j = j.sort_values(["gbif_id", "stand"]).drop_duplicates("gbif_id")
    outside = obs["gbif_id"].nunique() - j["gbif_id"].nunique()
    return pd.DataFrame(j.drop(columns=["geometry", "index_right"])), int(outside)


def _stand(stands: gpd.GeoDataFrame, i: int):
    r = stands.iloc[i]
    return stand_from_row(r["sp_main"], r["sp_admix"], r["age"], r["hab"], r["partners"])


def habitat_eval(key: str, sp: Species, stands: gpd.GeoDataFrame, presence: set[int],
                 background: set[int]) -> dict:
    bg = sorted(background - presence)
    if len(bg) > BG_RATIO * len(presence):
        bg = sorted(rng_for(key).sample(bg, BG_RATIO * len(presence)))
    out = {"n_presence": len(presence), "n_background": len(bg)}
    if len(presence) < MIN_PRESENCES:
        return {**out, "status": TOO_FEW, "habitat": None}
    pres = sorted(presence)
    st_p = [_stand(stands, i) for i in pres]
    st_b = [_stand(stands, i) for i in bg]
    h_p = [habitat_score(s, sp) for s in st_p]
    h_b = [habitat_score(s, sp) for s in st_b]
    hi_p = sum(1 for h in h_p if h >= LIFT_H)
    hi_all = hi_p + sum(1 for h in h_b if h >= LIFT_H)
    base = len(pres) / (len(pres) + len(bg))
    lift = (hi_p / hi_all) / base if hi_all else None
    comp_p = [habitat_components(s, sp) for s in st_p]
    comp_b = [habitat_components(s, sp) for s in st_b]
    factors = {}
    for name in HABITAT_FACTORS:
        neutral = frozenset({name})
        factors[name] = {
            "auc": auc([c[name] for c in comp_p], [c[name] for c in comp_b]),
            "ablation_auc": auc([habitat_score(s, sp, neutral) for s in st_p],
                                [habitat_score(s, sp, neutral) for s in st_b]),
        }
    return {**out, "status": "ok",
            "habitat": {"auc": auc(h_p, h_b), "lift60": lift, "factors": factors}}


def weather_eval(key: str, sp: Species, obs: pd.DataFrame,
                 series: Callable[[str, int], DailySeries | None]) -> dict:
    """AUC mnożnika w (i składowych): dni z obserwacją vs losowe dni sezonu w tej samej komórce."""
    rng = rng_for(key + ":wx")
    pres = sorted({(cell_id(la, lo), d) for la, lo, d in zip(obs["lat"], obs["lon"], obs["date"])})
    seen: dict[str, set] = defaultdict(set)
    for cell, d in pres:
        seen[cell].add(d)
    margin = timedelta(days=SEASON_MARGIN_DAYS)
    pos: list[WeatherComponents] = []
    neg: list[WeatherComponents] = []
    skipped = 0
    for cell, d in pres:
        s = series(cell, d.year) if d >= HIST_START else None
        if s is None or d not in s.dates:
            skipped += 1
            continue
        pos.append(weather_multiplier(s, s.dates.index(d), sp))
        lo = date(d.year, *sp.season_start) - margin
        hi = date(d.year, *sp.season_end) + margin
        cands = [k for k, x in enumerate(s.dates) if lo <= x <= hi and x not in seen[cell]]
        for k in rng.sample(cands, min(WX_BG_PER_PRESENCE, len(cands))):
            neg.append(weather_multiplier(s, k, sp))
    out = {"n": len(pos), "n_skipped": skipped, "n_background": len(neg)}
    if len(pos) < MIN_PRESENCES:
        return {**out, "status": TOO_FEW}
    return {**out, "status": "ok",
            "auc": auc([c.w for c in pos], [c.w for c in neg]),
            "components": {name: auc([getattr(c, name) for c in pos], [getattr(c, name) for c in neg])
                           for name in WX_COMPONENTS}}
