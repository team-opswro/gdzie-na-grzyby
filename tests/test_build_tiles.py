import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon, box

from forecast.species import load_species
from pipeline.build_tiles import (compute_features, mark_reserves, tippecanoe_cmd,
                                  write_centroids, write_geojsonseq, write_reserves_seq)
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


RES = gpd.GeoDataFrame({"name": ["Góra Św. Anny"]}, geometry=[box(17.0, 50.0, 17.5, 50.5)], crs=4326)


def test_mark_reserves_by_polygon_and_flag():
    f = compute_features(gdf_from([sq(50.2, 17.2), sq(50.8, 17.9), sq(50.9, 17.9)]), S)
    f["fun"] = [None, "REZ", "GOSP"]
    m = mark_reserves(f, RES)
    assert list(m["rez"]) == ["Góra Św. Anny", "rezerwat", None]
    assert "rez" not in f.columns


def test_mark_reserves_gdos_name_wins_over_flag():
    f = compute_features(gdf_from([sq(50.2, 17.2)]), S)
    f["fun"] = ["REZ"]
    assert mark_reserves(f, RES).loc[0, "rez"] == "Góra Św. Anny"


def test_mark_reserves_uses_representative_point():
    f = compute_features(gdf_from([box(17.49, 50.2, 17.7, 50.3)]), S)
    assert mark_reserves(f, RES).loc[0, "rez"] is None


def test_mark_reserves_without_fun_column_and_reserves():
    f = compute_features(gdf_from([sq(50.2, 17.2)]), S)
    assert mark_reserves(f, None).loc[0, "rez"] is None


def test_mark_reserves_overlap_takes_first():
    res = gpd.GeoDataFrame({"name": ["A", "B"]},
                           geometry=[box(17.0, 50.0, 17.5, 50.5), box(17.1, 50.1, 17.4, 50.4)],
                           crs=4326)
    f = compute_features(gdf_from([sq(50.2, 17.2)]), S)
    m = mark_reserves(f, res)
    assert len(m) == 1 and m.loc[0, "rez"] == "A"


def test_centroids_skip_reserves(tmp_path):
    f = mark_reserves(compute_features(gdf_from([sq(50.2, 17.2), sq(50.8, 17.9)]), S), RES)
    p = tmp_path / "c.json"
    assert write_centroids(f, KEYS, p) == 1
    assert json.load(open(p))["rows"][0][0] == "id1"


def test_geojsonseq_has_rez(tmp_path):
    f = mark_reserves(compute_features(gdf_from([sq(50.2, 17.2), sq(50.8, 17.9)]), S), RES)
    p = tmp_path / "l.seq"
    write_geojsonseq(f, KEYS, p)
    a, b = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]
    assert a["properties"]["rez"] == "Góra Św. Anny"
    assert "rez" not in b["properties"]


def test_write_reserves_seq(tmp_path):
    p = tmp_path / "r.seq"
    write_reserves_seq(RES, p)
    o = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert o["properties"] == {"name": "Góra Św. Anny"}
    assert o["geometry"]["type"] == "Polygon"


def test_tippecanoe_cmd_two_layers(tmp_path):
    cmd = tippecanoe_cmd(tmp_path, {"lasy": Path("a.seq"), "rezerwaty": Path("r.seq")})
    assert cmd[:3] == ["tippecanoe", "-o", str(tmp_path / "lasy.pmtiles")]
    assert "-L" in cmd and "lasy:a.seq" in cmd and "rezerwaty:r.seq" in cmd and "-l" not in cmd
    assert "-Z8" in cmd and "-z14" in cmd and "--force" in cmd


def test_mark_reserves_null_name_still_marked(tmp_path):
    res = gpd.GeoDataFrame({"name": [None]}, geometry=[box(17.0, 50.0, 17.5, 50.5)], crs=4326)
    f = compute_features(gdf_from([sq(50.2, 17.2), sq(50.8, 17.9)]), S)
    m = mark_reserves(f, res)
    assert list(m["rez"]) == ["rezerwat", None]
    p = tmp_path / "c.json"
    assert write_centroids(m, KEYS, p) == 1


def test_write_reserves_seq_null_name_is_valid_json(tmp_path):
    res = gpd.GeoDataFrame({"name": [None]}, geometry=[box(17.0, 50.0, 17.5, 50.5)], crs=4326)
    p = tmp_path / "r.seq"
    write_reserves_seq(res, p)

    def boom(c):
        raise ValueError(c)
    o = json.loads(p.read_text(encoding="utf-8").splitlines()[0], parse_constant=boom)
    assert "name" not in o["properties"]
