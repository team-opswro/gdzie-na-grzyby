from datetime import date, timedelta

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from forecast.species import load_species
from pipeline.habitat import HABITAT_FACTORS
from forecast.model import DailySeries
from pipeline.grid import cell_id
from pipeline.validate import BG_RATIO, TOO_FEW, auc, habitat_eval, join_stands, weather_eval

S = load_species()
GOOD = ("SO", (), 80, "BSW", ())   # borowik/podgrzybek: h = 1
BAD = ("OL", (), 60, "OL", ())     # h = 0 dla wszystkich


def stands_gdf(kinds, size=0.01):
    """Kwadraty w rzędzie; kinds = lista krotek (sp_main, sp_admix, age, hab, partners)."""
    rows = []
    for i, (sp, adm, age, hab, pt) in enumerate(kinds):
        rows.append({"id": f"s{i}", "sp_main": sp, "sp_admix": adm, "partners": pt, "age": age,
                     "hab": hab, "geometry": box(17 + i * size, 50, 17 + (i + 1) * size, 50 + size)})
    return gpd.GeoDataFrame(rows, crs=4326)


def test_auc_known_cases():
    assert auc([3, 4], [1, 2]) == 1.0
    assert auc([1, 2], [3, 4]) == 0.0
    assert auc([1, 1], [1, 1]) == 0.5
    assert auc([], [1]) is None and auc([1], []) is None


def test_join_counts_outside_and_dedupes_overlap():
    st = gpd.GeoDataFrame({"id": ["a", "b"]}, geometry=[box(0, 0, 2, 2), box(1, 1, 3, 3)], crs=4326)
    obs = pd.DataFrame({"species": ["x", "x"], "gbif_id": [1, 2], "lat": [1.5, 9.0],
                        "lon": [1.5, 9.0], "date": [date(2023, 9, 1)] * 2})
    joined, outside = join_stands(obs, st)
    assert outside == 1
    assert list(joined["gbif_id"]) == [1] and list(joined["stand"]) == [0]


def test_too_few_presences():
    st = stands_gdf([GOOD] * 200)
    r = habitat_eval("borowik", S["borowik"], st, presence=set(range(29)), background=set(range(29, 200)))
    assert r["status"] == "za mało danych" and r["habitat"] is None and r["n_presence"] == 29


def test_perfect_separation_auc_one():
    st = stands_gdf([GOOD] * 30 + [BAD] * 100)
    r = habitat_eval("borowik", S["borowik"], st, presence=set(range(30)), background=set(range(30, 130)))
    assert r["status"] == "ok"
    assert r["habitat"]["auc"] == 1.0
    assert r["habitat"]["lift60"] == pytest.approx(130 / 30)


def test_background_sample_capped_and_deterministic():
    st = stands_gdf([GOOD] * 30 + [BAD, GOOD] * 500)
    args = ("borowik", S["borowik"], st, set(range(30)), set(range(30, 1030)))
    r1, r2 = habitat_eval(*args), habitat_eval(*args)
    assert r1["n_background"] == BG_RATIO * 30 == 600
    assert r1 == r2


def test_species_subset_independent():
    st = stands_gdf([GOOD] * 30 + [BAD, GOOD] * 500)
    args = (st, set(range(30)), set(range(30, 1030)))
    alone = habitat_eval("kurka", S["kurka"], *args)
    habitat_eval("borowik", S["borowik"], *args)
    assert habitat_eval("kurka", S["kurka"], *args) == alone


def test_empty_background_gives_none_auc():
    st = stands_gdf([GOOD] * 30)
    r = habitat_eval("borowik", S["borowik"], st, presence=set(range(30)), background=set(range(30)))
    assert r["habitat"]["auc"] is None and r["n_background"] == 0


def test_factor_ablation_keys():
    st = stands_gdf([GOOD] * 30 + [BAD] * 30)
    r = habitat_eval("borowik", S["borowik"], st, set(range(30)), set(range(30, 60)))
    f = r["habitat"]["factors"]
    assert set(f) == set(HABITAT_FACTORS)
    assert all(set(v) == {"auc", "ablation_auc"} for v in f.values())


# --- pogoda ---

PRES_DAY = date(2023, 9, 15)


def wet_series():
    """2023-04-10..2023-11-30; 5 mm/dzień tylko 1–8 września -> pełny opad (8×5 = 40) wyłącznie
    w dniu PRES_DAY (dni 7–14 wstecz); temperatura i wilgotność gleby optymalne."""
    start, end = date(2023, 4, 10), date(2023, 11, 30)
    dates = [start + timedelta(days=k) for k in range((end - start).days + 1)]
    precip = [5.0 if date(2023, 9, 1) <= d <= date(2023, 9, 8) else 0.0 for d in dates]
    return DailySeries(dates=dates, precip=precip, soil_temp=[15.0] * len(dates),
                       soil_moisture=[0.3] * len(dates))


def obs_df(n, day=PRES_DAY, lat0=50.05):
    return pd.DataFrame({"species": ["borowik"] * n, "gbif_id": range(n),
                         "lat": [lat0 + 0.1 * i for i in range(n)], "lon": [18.05] * n,
                         "date": [day] * n})


def series_for(s):
    return lambda cell, year: s if year == 2023 else None


def test_weather_auc_one_when_presence_days_wet():
    r = weather_eval("borowik", S["borowik"], obs_df(30), series_for(wet_series()))
    assert r["n"] == 30 and r["n_skipped"] == 0
    assert r["auc"] == 1.0
    assert {"rain", "temp", "season"} <= set(r["components"]) and "w" not in r["components"]


def test_weather_skips_out_of_range_dates():
    extra = pd.DataFrame({"species": ["borowik"] * 2, "gbif_id": [100, 101], "lat": [52.05, 52.15],
                          "lon": [18.05, 18.05], "date": [date(2021, 9, 1), date(2023, 12, 15)]})
    r = weather_eval("borowik", S["borowik"], pd.concat([obs_df(30), extra]), series_for(wet_series()))
    assert r["n"] == 30 and r["n_skipped"] == 2


def test_weather_series_none_skipped():
    s = wet_series()
    skip_cell = cell_id(50.05, 18.05)
    r = weather_eval("borowik", S["borowik"], obs_df(31),
                     lambda cell, year: None if cell == skip_cell else s)
    assert r["n"] == 30 and r["n_skipped"] == 1


def test_weather_background_excludes_presence_days_and_is_deterministic():
    # jedna komórka, obserwacje we wszystkie dni okna sezonu poza jednym -> tło tylko z tego dnia
    s = wet_series()
    days = [d for d in s.dates if date(2023, 6, 17) <= d <= date(2023, 11, 14) and d != date(2023, 8, 1)]
    obs = pd.DataFrame({"species": "borowik", "gbif_id": range(len(days)), "lat": 50.05, "lon": 18.05,
                        "date": days})
    r1 = weather_eval("borowik", S["borowik"], obs, series_for(s))
    r2 = weather_eval("borowik", S["borowik"], obs, series_for(s))
    assert r1 == r2 and r1["n_background"] == len(days)  # każda obecność losuje jedyny wolny dzień


def test_weather_too_few():
    r = weather_eval("borowik", S["borowik"], obs_df(10), series_for(wet_series()))
    assert r["status"] == TOO_FEW and r["n"] == 10
