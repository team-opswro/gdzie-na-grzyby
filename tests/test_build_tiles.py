import json

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon, box

from forecast.species import load_species
from pipeline.build_tiles import compute_features, write_centroids
from pipeline.grid import cell_id
from pipeline.habitat import Stand

S = load_species()
KEYS = list(S)


def gdf_from(geoms, stands=None):
    stands = stands or [Stand("SO", (), 80, "BSW")] * len(geoms)
    return gpd.GeoDataFrame(
        {
            "id": [f"id{i}" for i in range(len(geoms))],
            "sp_main": [s.sp_main for s in stands],
            "sp_admix": [s.sp_admix for s in stands],
            "age": pd.array([s.age for s in stands], dtype="Int64"),
            "hab": [s.hab for s in stands],
        },
        geometry=list(geoms),
        crs=4326,
    )


def sq(lat, lon, d=0.001):
    return box(lon, lat, lon + d, lat + d)


def test_h_columns_and_values():
    f = compute_features(gdf_from([sq(50.7, 17.9)]), S)
    assert f.loc[0, "h_podgrzybek"] == 100 and f.loc[0, "h_borowik"] == 100
    assert f.loc[0, "h_kozlarz"] == 0
    assert all(f"h_{k}" in f.columns for k in KEYS)


def test_cell_from_representative_point():
    # litera C: centroid wypada w wycięciu (poza wielokątem), w innej komórce
    c_shape = Polygon([(17.0, 50.0), (17.5, 50.0), (17.5, 50.05), (17.01, 50.05),
                       (17.01, 50.95), (17.5, 50.95), (17.5, 51.0), (17.0, 51.0)])
    assert not c_shape.contains(c_shape.centroid)
    f = compute_features(gdf_from([c_shape]), S)
    rp = c_shape.representative_point()
    assert f.loc[0, "cell"] == cell_id(rp.y, rp.x)
    assert f.loc[0, "cell"] != cell_id(c_shape.centroid.y, c_shape.centroid.x)
    assert f.loc[0, "lat"] == rp.y and f.loc[0, "lon"] == rp.x


def test_clipped_to_boundary():
    boundary = box(17.0, 50.0, 17.5, 51.0)
    half = box(17.4, 50.5, 17.6, 50.6)       # w połowie poza granicą
    outside = box(18.0, 50.5, 18.1, 50.6)
    inside = box(17.1, 50.5, 17.2, 50.6)
    f = compute_features(gdf_from([half, outside, inside]), S, boundary)
    assert list(f["id"]) == ["id0", "id2"]
    assert abs(f.geometry.iloc[0].area - half.area / 2) < 1e-9
    assert f.geometry.iloc[0].bounds[2] <= 17.5 + 1e-9
    # punkt reprezentatywny liczony po przycięciu
    assert f.loc[f.index[0], "lon"] <= 17.5


def test_centroids_threshold(tmp_path):
    # SO 80 BSW => 100; BRZ 3 lata => same zera; potrzebny wynik 39/40
    f = compute_features(gdf_from([sq(50.7, 17.9), sq(50.8, 17.9)],
                                  [Stand("SO", (), 80, "BSW"), Stand("OL", (), 60, "OL")]), S)
    f["h_borowik"] = [40, 0]
    f.loc[1, "h_borowik"] = 39
    for k in KEYS[1:]:
        f[f"h_{k}"] = 0
    p = tmp_path / "c.json"
    assert write_centroids(f, KEYS, p) == 1
    d = json.load(open(p))
    assert d["species"] == KEYS
    row = d["rows"][0]
    assert row[0] == "id0" and len(row) == 4 + len(KEYS) and row[4] == 40
    assert row[1] == round(f.loc[0, "lat"], 5)
