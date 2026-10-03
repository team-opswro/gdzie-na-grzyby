"""Walidacja modelu na obserwacjach GBIF (spec H): AUC/lift siedliska i AUC pogody per gatunek.

Raport offline: pipeline/data/walidacja/ (nie out/ — publish wysyła cały katalog builda).
"""
import argparse
import dataclasses
import json
import random
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Sequence

import geopandas as gpd
import pandas as pd
import yaml

from forecast.model import DailySeries, WeatherComponents, weather_multiplier
from forecast.species import ROOT, Species, load_species
from pipeline.gbif import load_observations
from pipeline.grid import cell_id
from pipeline.habitat import HABITAT_FACTORS, habitat_components, habitat_score, stand_from_row
from pipeline.ingest import DATA_DIR, DEFAULT_DB, DEFAULT_PARQUET, load_stands
from pipeline.meteo_hist import HIST_START, fetch_year

MIN_PRESENCES = 30
BG_RATIO = 20
LIFT_H = 0.6
SEED = 0
TOO_FEW = "za mało danych"
WX_BG_PER_PRESENCE = 5
SEASON_MARGIN_DAYS = 14
DEFAULT_OUT = DATA_DIR / "walidacja"
DEFAULT_AREA = DATA_DIR / "obszar.geojson"
DEFAULT_CACHE = DATA_DIR / "raw"
CONTENT_PATH = ROOT / "content" / "gatunki.yaml"
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


# --- raport ---

def build_report(per_species: dict[str, dict], *, build: str | None, generated_at: str, outside: int,
                 warnings: list[str]) -> dict:
    return {"generated_at": generated_at, "build": build, "outside": outside, "warnings": warnings,
            "species": per_species}


def _f(v, fmt="{:.3f}") -> str:
    return "—" if v is None else fmt.format(v)


def render_md(report: dict, baseline: dict | None = None) -> str:
    base = (baseline or {}).get("species", {})
    out = ["# Walidacja modelu na obserwacjach GBIF", "",
           f"Wygenerowano: {report['generated_at']} · build: {report.get('build') or '—'} · "
           f"obserwacje poza wydzieleniami: {report.get('outside', 0)}", ""]
    for w in report.get("warnings", []):
        out.append(f"- Uwaga: {w}")
    out += ["", "## Siedlisko", ""]
    head = "| Gatunek | Obecności | Tło | AUC | Lift (h ≥ 60) |"
    out += [head + (" Δ AUC |" if baseline else ""), "|---|---|---|---|---|" + ("---|" if baseline else "")]
    factor_rows = []
    for key, r in report["species"].items():
        hab = r.get("habitat")
        if r.get("status") != "ok" or hab is None:
            out.append(f"| {key} | {TOO_FEW} (n={r.get('n_presence', 0)}) | | | |" + (" |" if baseline else ""))
            continue
        row = f"| {key} | {r['n_presence']} | {r['n_background']} | {_f(hab['auc'])} | {_f(hab['lift60'], '{:.2f}')} |"
        if baseline:
            b = (base.get(key) or {}).get("habitat") or {}
            delta = None if hab["auc"] is None or b.get("auc") is None else hab["auc"] - b["auc"]
            row += f" {_f(delta, '{:+.3f}')} |"
        out.append(row)
        for name, f in hab["factors"].items():
            factor_rows.append(f"| {key} | {name} | {_f(f['auc'])} | {_f(f['ablation_auc'])} |")
    out += ["", "## Czynniki siedliska", "", "| Gatunek | Czynnik | AUC czynnika | AUC h bez czynnika |",
            "|---|---|---|---|", *factor_rows, "", "## Pogoda", ""]
    out += ["| Gatunek | Obecności (dni) | Pominięte | AUC w | Składowe |", "|---|---|---|---|---|"]
    for key, r in report["species"].items():
        wx = r.get("weather")
        if wx is None:
            out.append(f"| {key} | — | | | |")
        elif wx.get("status") != "ok":
            out.append(f"| {key} | {TOO_FEW} (n={wx['n']}) | {wx['n_skipped']} | | |")
        else:
            comps = ", ".join(f"{k} {_f(v)}" for k, v in wx["components"].items())
            out.append(f"| {key} | {wx['n']} | {wx['n_skipped']} | {_f(wx['auc'])} | {comps} |")
    return "\n".join(out) + "\n"


def load_area(path: Path):
    return gpd.read_file(path).to_crs(4326).union_all()


def _latin_by_key(keys: list[str]) -> dict[str, str]:
    content = yaml.safe_load(CONTENT_PATH.read_text(encoding="utf-8"))
    return {k: content["species"][k]["latin"] for k in keys}


def _build_id() -> str | None:
    p = DATA_DIR / "out" / "build.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("build")
    except (OSError, ValueError):
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--species", help="klucze po przecinku (domyślnie wszystkie)")
    ap.add_argument("--refresh", action="store_true", help="pobierz ponownie zamiast z cache")
    ap.add_argument("--no-weather", action="store_true")
    ap.add_argument("--compare", type=Path, help="poprzedni walidacja.json (kolumna Δ AUC)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--parquet", type=Path, default=DEFAULT_PARQUET)
    ap.add_argument("--area", type=Path, default=DEFAULT_AREA)
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    args = ap.parse_args(argv)

    species = load_species()
    keys = args.species.split(",") if args.species else list(species)
    unknown = [k for k in keys if k not in species]
    if unknown:
        ap.error(f"nieznane gatunki: {', '.join(unknown)}")
    today = date.today()
    area = load_area(args.area)
    print("wczytywanie wydzieleń…", file=sys.stderr)
    stands = load_stands(args.db, args.parquet)
    pres, bg, warnings = load_observations(_latin_by_key(keys), area, args.cache / "gbif",
                                           refresh=args.refresh, year_to=today.year)
    pres_j, outside = join_stands(pres, stands) if len(pres) else (pres.assign(stand=[]), 0)
    bg_j, _ = join_stands(bg, stands) if len(bg) else (bg.assign(stand=[]), 0)
    background = set(bg_j["stand"])

    cache: dict[tuple[str, int], DailySeries | None] = {}

    def series(cell: str, year: int):
        if (cell, year) not in cache:
            cache[(cell, year)] = fetch_year(cell, year, args.cache / "meteo", today=today,
                                             refresh=args.refresh)
        return cache[(cell, year)]

    per_species = {}
    for key in keys:
        presence = set(pres_j.loc[pres_j["species"] == key, "stand"])
        r = habitat_eval(key, species[key], stands, presence, background)
        if args.no_weather:
            r["weather"] = None
        else:
            obs = pres[pres["species"] == key]
            print(f"pogoda: {key} ({len(obs)} obserwacji)", file=sys.stderr)
            r["weather"] = weather_eval(key, species[key], obs, series)
        per_species[key] = r

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = build_report(per_species, build=_build_id(), generated_at=now, outside=outside,
                          warnings=warnings)
    baseline = json.loads(args.compare.read_text(encoding="utf-8")) if args.compare else None
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "walidacja.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    (args.out / "walidacja.md").write_text(render_md(report, baseline), encoding="utf-8")
    print(f"raport: {args.out / 'walidacja.md'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
