"""Przypadek z terenu (spec L, 2026-10-04): wyniki dwóch wydzieleń w kratce 505_176.

Pogoda dnia z fikstury tests/fixtures/m_case_505_176.json (Open-Meteo), liczona bieżącym modelem (spec M).

379-b — pagórkowate, zacienione, sucho, pusto; 370-a — brzeg Stawu Pustelnik, pełny koszyk.
Uruchomienie (po pipeline.wetness): PYTHONPATH=. .venv/bin/python scripts/check_wet_case.py
"""
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from forecast.model import DailySeries, weather_multiplier, wet_adjust
from forecast.species import load_species
from pipeline.build_tiles import STAND_EXTRA
from pipeline.habitat import habitat_score, stand_from_row
from pipeline.ingest import DATA_DIR, DEFAULT_DB, DEFAULT_PARQUET, load_stands

DRY, WET = "02-32-1-04-379-b-99", "02-32-1-04-370-a-00"
CASE = Path(__file__).resolve().parent.parent / "tests/fixtures/m_case_505_176.json"
DAY = date(2026, 10, 4)
SPECIES = ("borowik", "borowik_sosnowy", "podgrzybek", "kozlarz", "kurka")


def main() -> int:
    sps = load_species()
    raw = json.loads(CASE.read_text())
    raw["dates"] = [date.fromisoformat(d) for d in raw["dates"]]
    s = DailySeries(**raw)
    comps = {k: weather_multiplier(s, s.dates.index(DAY), sps[k]) for k in SPECIES}
    st = load_stands(DEFAULT_DB, DEFAULT_PARQUET)
    st = st[st["id"].isin([DRY, WET])].set_index("id")
    if len(st) != 2:
        print("brak wydzieleń przypadku w danych", file=sys.stderr)
        return 1
    rows = []
    for sid, r in st.iterrows():
        stand = stand_from_row(r.sp_main, r.sp_admix, r.age, r.hab, r.partners,
                               **{c: r[c] for c in STAND_EXTRA})
        wet = None if pd.isna(r["wet"]) else float(r["wet"])
        row = {"id": sid, "wet": wet, "wl": r["wl"]}
        for k in SPECIES:
            h = round(100 * habitat_score(stand, sps[k]))
            c = comps[k]
            row[k] = f"{round(h * c.w)} -> {round(h * wet_adjust(c.w, c.moist, wet, sps[k].wet_gamma))}"
        rows.append(row)
    print(pd.DataFrame(rows).set_index("id").to_string())
    w = ", ".join(f"{k} w={c.w:.2f} moist={c.moist:.2f}" for k, c in comps.items())
    print(f"(wynik dnia bez wilgotności -> z wilgotnością; {w}; dane: {DATA_DIR})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
