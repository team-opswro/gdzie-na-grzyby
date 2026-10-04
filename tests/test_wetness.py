import numpy as np
import pandas as pd
import geopandas as gpd
import pytest
from shapely.geometry import LineString, box

from pipeline import wetness as wt

CFG = wt.load_config()


def test_config_weights_sum_to_one_and_sets_expanded():
    assert sum(CFG.weights.values()) == pytest.approx(1.0)
    assert CFG.habitat_types["OL"] == 1.0 and CFG.habitat_types["BMW"] == 0.6   # @bory_mieszane_wilgotne
    assert CFG.habitat_types["BS"] == 0.0 and "BMSW" not in CFG.habitat_types   # świeże -> default


def test_dist_value():
    v = wt.dist_value([0, 50, 275, 500, 900, np.nan], 50, 500)
    assert v.tolist() == pytest.approx([1, 1, 0.5, 0, 0, 0])


@pytest.mark.parametrize("hab,moist,exp", [
    ("OL", None, 1.0), ("BMSW", "S", 0.2), ("BMSW", "LZ", 0.9), ("BS", "SU", 0.0),
    ("BMW", "WW", 0.6), (None, None, wt.NEUTRAL), ("BMSW", "XX", 0.2)])
def test_habitat_value(hab, moist, exp):
    assert wt.habitat_value(hab, moist, CFG) == pytest.approx(exp)


@pytest.mark.parametrize("soil,exp", [
    ("Gw", 1.0), ("OGw", 1.0), ("MRm", 1.0), ("MDb", 0.7), ("Bgms", 0.5), ("Bw", 0.0),
    ("RDw", 0.0), ("Pog", 0.5), (None, wt.NEUTRAL)])
def test_soil_value(soil, exp):
    assert wt.soil_value(soil, CFG) == pytest.approx(exp)


def _df(n=10, **over):
    base = {"d_water": [np.nan] * n, "d_ditch": [np.nan] * n, "tpi": np.linspace(-5, 5, n),
            "twi": [7.0] * n, "hab": ["BMSW"] * n, "moist": ["S"] * n, "soil": ["Bw"] * n}
    base.update(over)
    return pd.DataFrame(base)


def test_combine_lakeshore_wetter_than_hilltop():
    # 0: brzeg stawu w obniżeniu, gleba oglejona; 9: wierzchowina daleko od wody
    df = _df(d_water=[3] + [np.nan] * 9, soil=["Bgms"] + ["Bw"] * 9)
    r = wt.combine(df, CFG)
    assert r.loc[0, "wet"] == 100 and r.loc[9, "wet"] < 20
    assert r.loc[0, "wl"] == "water" and r.loc[9, "wl"] == "hilltop"
    assert r["wet"].between(0, 100).all()


def test_combine_median_is_about_50():
    rng = np.random.default_rng(0)
    df = _df(200, tpi=rng.normal(size=200), twi=rng.normal(7, 1, size=200))
    assert np.median(wt.combine(df, CFG)["wet"]) == pytest.approx(50, abs=2)


def test_combine_missing_terrain_neutral():
    r = wt.combine(_df(4, tpi=[np.nan] * 4, twi=[np.nan] * 4), CFG)
    assert (r["valley"] == wt.NEUTRAL).all() and (r["twi"] == wt.NEUTRAL).all()


def test_nearest_dist_edge_to_edge():
    st = gpd.GeoDataFrame(geometry=[box(0, 0, 100, 100), box(1000, 0, 1100, 100)], crs=2180)
    feats = gpd.GeoDataFrame(geometry=[LineString([(130, 0), (130, 100)])], crs=2180)
    d = wt.nearest_dist(st, feats, 500)
    assert d[0] == pytest.approx(30) and np.isnan(d[1])


def test_nan_codes_are_missing():
    assert wt.soil_value(float("nan"), CFG) == wt.NEUTRAL
    assert wt.habitat_value(float("nan"), float("nan"), CFG) == wt.NEUTRAL
