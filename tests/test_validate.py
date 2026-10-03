from datetime import date

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from forecast.species import load_species
from pipeline.habitat import HABITAT_FACTORS
from pipeline.validate import BG_RATIO, auc, habitat_eval, join_stands

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
