import numpy as np
import pytest

from pipeline.terrain import (
    circular_mean_deg, exposure_class, flow_accumulation, slope_aspect, twi, twi_classes,
)


def valley(n=50):
    """Dolina w kształcie V wzdłuż kolumny n//2, opadająca lekko na południe (wiersze rosną)."""
    x = np.arange(n)
    return np.tile(np.abs(x - n // 2).astype(float) * 2.0, (n, 1)) + np.linspace(10, 0, n)[:, None]


def test_valley_twi_higher_than_ridge():
    dem = valley()
    slope, _ = slope_aspect(dem)
    t = twi(flow_accumulation(dem), slope)
    assert t[25, 25] > t[25, 2]


def test_flat_dem_finite_twi():
    dem = np.full((20, 20), 100.0)
    slope, _ = slope_aspect(dem)
    assert np.isfinite(twi(flow_accumulation(dem), slope)).all()


def test_aspect_south_and_north_planes():
    rows = np.arange(30, dtype=float)[:, None] * np.ones((1, 30))
    south = 100 - rows * 3   # wysokość spada ku południowi (wiersze w dół)
    north = 100 + rows * 3
    _, a_s = slope_aspect(south)
    _, a_n = slope_aspect(north)
    assert a_s[15, 15] == pytest.approx(180, abs=1)
    assert min(a_n[15, 15], 360 - a_n[15, 15]) < 1


def test_circular_mean_wraps_north():
    s = (np.sin(np.radians(350)) + np.sin(np.radians(10))) / 2
    c = (np.cos(np.radians(350)) + np.cos(np.radians(10))) / 2
    m = circular_mean_deg(s, c)
    assert m < 1 or m > 359


def test_nodata_does_not_poison_neighbours():
    dem = valley(30)
    dem[0, :] = dem[-1, :] = dem[:, 0] = dem[:, -1] = -9999.0
    slope, _ = slope_aspect(dem, nodata=-9999.0)
    t = twi(flow_accumulation(dem, nodata=-9999.0), slope)
    assert np.isfinite(t[5:25, 5:25]).all()
    assert np.isnan(t[0, 0])


def test_twi_classes_terciles():
    classes, (t1, t2) = twi_classes(np.arange(1, 10, dtype=float))
    assert (t1, t2) == pytest.approx((11 / 3, 19 / 3))
    assert classes == ["DRY"] * 3 + ["MID"] * 3 + ["WET"] * 3


def test_exposure_class():
    assert exposure_class(15, 180) == "S_STEEP"
    assert exposure_class(5, 180) == "OTHER"
    assert exposure_class(15, 0) == "OTHER"
    assert exposure_class(15, 135) == "S_STEEP"
    assert exposure_class(15, 226) == "OTHER"
