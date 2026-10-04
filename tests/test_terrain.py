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


# --- I/O: kafle GLO-30, statystyki strefowe, CLI ---

import geopandas as gpd
import pyarrow.parquet as pq
import responses
from affine import Affine
from shapely.geometry import box

from pipeline import terrain
from pipeline.terrain import DEM_URL, download_tiles, main, tile_names, zonal


def test_tile_names_for_bbox():
    names = tile_names((17.2, 49.4, 19.8, 51.1))
    assert sorted(names) == [(la, lo) for la in (49, 50, 51) for lo in (17, 18, 19)]


def test_dem_url_format():
    assert DEM_URL.format(lat=50, lon=18) == (
        "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N50_00_E018_00_DEM/"
        "Copernicus_DSM_COG_10_N50_00_E018_00_DEM.tif")


@responses.activate
def test_download_skips_404_and_caches(tmp_path):
    responses.get(DEM_URL.format(lat=50, lon=18), body=b"TIFF")
    responses.get(DEM_URL.format(lat=50, lon=19), status=404)
    paths = download_tiles([(50, 18), (50, 19)], tmp_path)
    assert [p.name for p in paths] == ["N50_E018.tif"] and paths[0].read_bytes() == b"TIFF"
    again = download_tiles([(50, 18), (50, 19)], tmp_path)
    assert again == paths and len(responses.calls) == 3  # 404 pytany ponownie, 200 z cache


def _grid():
    """Raster 2180: 20×20 pikseli 30 m od (500000, 300600) w dół; wartości = numer kolumny."""
    tr = Affine(30, 0, 500000, 0, -30, 300600)
    vals = np.tile(np.arange(20, dtype=float), (20, 1))
    return tr, vals


def test_zonal_two_polygons_epsg2180():
    tr, vals = _grid()
    st = gpd.GeoDataFrame({"prefix": ["p", "p"], "a_i_num": [1, 2]},
                          geometry=[box(500000, 300300, 500150, 300600),   # kolumny 0–4
                                    box(500300, 300300, 500450, 300600)],  # kolumny 10–14
                          crs=2180)
    asp = np.full((20, 20), 180.0)
    df = zonal(st, twi=vals, slope=vals * 2, aspect=asp, transform=tr)
    assert list(df.columns) == ["prefix", "a_i_num", "twi", "slope", "aspect"]
    r = df.set_index("a_i_num")
    assert r.loc[1, "twi"] == pytest.approx(2.0) and r.loc[2, "twi"] == pytest.approx(12.0)
    assert r.loc[2, "slope"] == pytest.approx(24.0) and r.loc[1, "aspect"] == pytest.approx(180.0)


def test_tiny_polygon_gets_pixel():
    tr, vals = _grid()
    st = gpd.GeoDataFrame({"prefix": ["p"], "a_i_num": [7]},
                          geometry=[box(500100, 300500, 500105, 300505)], crs=2180)  # 5×5 m
    df = zonal(st, twi=vals, slope=vals, aspect=np.zeros((20, 20)), transform=tr)
    assert len(df) == 1 and df.iloc[0]["twi"] == pytest.approx(3.0)


def test_main_writes_parquet_with_metadata(tmp_path, monkeypatch):
    area = tmp_path / "obszar.geojson"
    gpd.GeoDataFrame({"n": [1]}, geometry=[box(18.0, 50.0, 18.05, 50.05)], crs=4326).to_file(area)
    stands = gpd.GeoDataFrame({"prefix": ["p"] * 3, "a_i_num": [1, 2, 3], "id": ["a", "b", "c"]},
                              geometry=[box(18.005 + 0.01 * i, 50.01, 18.012 + 0.01 * i, 50.02)
                                        for i in range(3)], crs=4326)
    stands.to_parquet(tmp_path / "stands.parquet")
    monkeypatch.setattr(terrain, "download_tiles", lambda tiles, cache, **k: [tmp_path / "fake.tif"])

    def fake_window(paths, bounds_2180):
        minx, miny, maxx, maxy = bounds_2180
        w, h = int((maxx - minx) // 30) + 1, int((maxy - miny) // 30) + 1
        x = np.arange(w)
        dem = np.tile(np.abs(x - w // 2).astype(float), (h, 1)) + np.linspace(50, 0, h)[:, None]
        return dem, Affine(30, 0, minx, 0, -30, maxy)
    monkeypatch.setattr(terrain, "window_dem", fake_window)
    out = tmp_path / "terrain.parquet"
    assert main(["--area", str(area), "--parquet", str(tmp_path / "stands.parquet"), "--out", str(out),
                 "--cache", str(tmp_path / "c")]) == 0
    df = pq.read_table(out).to_pandas()
    assert set(df["a_i_num"]) == {1, 2, 3}
    assert "tpi" in df.columns and df["tpi"].notna().all()
    assert set(df["twi_class"]) <= {"DRY", "MID", "WET"} and set(df["exposure"]) <= {"S_STEEP", "OTHER"}
    meta = pq.read_schema(out).metadata
    assert b"twi_terciles" in meta and meta[b"dem"] == b"GLO-30"


# --- TPI (spec L) ---

def test_tpi_hill_positive_valley_negative():
    from pipeline.terrain import tpi
    y, x = np.mgrid[0:61, 0:61]
    r = np.hypot(x - 30, y - 30)
    hill = 100 - r          # stożek: szczyt wyżej niż średnia otoczenia
    t = tpi(hill, window_m=900)
    assert t[30, 30] > 5 and abs(t[30, 0]) < abs(t[30, 30])
    assert tpi(-hill, window_m=900)[30, 30] < -5


def test_tpi_flat_zero_and_nodata():
    from pipeline.terrain import tpi
    z = np.full((20, 20), 200.0)
    z[0, 0] = -9999.0
    t = tpi(z, window_m=300, nodata=-9999.0)
    assert np.isnan(t[0, 0]) and np.nanmax(np.abs(t)) == pytest.approx(0.0)


def test_zonal_tpi_mean():
    tr, vals = _grid()
    st = gpd.GeoDataFrame({"prefix": ["p"], "a_i_num": [1]},
                          geometry=[box(500000, 300300, 500150, 300600)], crs=2180)  # kolumny 0–4
    df = zonal(st, twi=vals, slope=vals, aspect=np.zeros((20, 20)), transform=tr, tpi=vals - 10)
    assert df.iloc[0]["tpi"] == pytest.approx(-8.0)
