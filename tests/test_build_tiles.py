import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon, box

from tests.generic_species import generic_species
from forecast.species import load_species
from pipeline.build_tiles import (centroid_rows, compute_features, mark_reserves, tile_key, tippecanoe_cmd,
                                  write_centroid_tiles, write_geojsonseq, write_reserves_seq)
from pipeline.grid import cell_id
from pipeline.habitat import Stand

S = generic_species()
KEYS = list(S)


def gdf_from(geoms, stands=None):
    stands = stands or [Stand("SO", (), 80, "BSW")] * len(geoms)
    return gpd.GeoDataFrame(
        {
            "id": [f"id{i}" for i in range(len(geoms))],
            "sp_main": [s.sp_main for s in stands],
            "sp_admix": [s.sp_admix for s in stands],
            "partners": pd.Series([s.partners for s in stands], dtype=object).values,
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
    idx = write_centroid_tiles(f, KEYS, tmp_path)
    assert idx["species"] == KEYS and idx["tiles"] == ["50.5_17.5"]
    d = json.load(open(tmp_path / "50.5_17.5.json"))
    assert len(d["rows"]) == 1 and "species" not in d
    row = d["rows"][0]
    assert row[0] == "id0" and len(row) == 4 + len(KEYS) + 1 and row[4] == 40 and row[-1] is None
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
    idx = write_centroid_tiles(f, KEYS, tmp_path)
    assert idx["tiles"] == ["50.5_17.5"]
    assert [r[0] for r in json.load(open(tmp_path / "50.5_17.5.json"))["rows"]] == ["id1"]


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
    idx = write_centroid_tiles(m, KEYS, tmp_path)
    assert idx["tiles"] == ["50.5_17.5"]


def test_write_reserves_seq_null_name_is_valid_json(tmp_path):
    res = gpd.GeoDataFrame({"name": [None]}, geometry=[box(17.0, 50.0, 17.5, 50.5)], crs=4326)
    p = tmp_path / "r.seq"
    write_reserves_seq(res, p)

    def boom(c):
        raise ValueError(c)
    o = json.loads(p.read_text(encoding="utf-8").splitlines()[0], parse_constant=boom)
    assert "name" not in o["properties"]


def test_partners_change_scores():
    # dąb panujący (nie partner podgrzybka), sosna w domieszce z udziałem 4 i wiekiem 80
    base = Stand("DB", ("SO",), 80, "BSW", ())
    withp = Stand("DB", ("SO",), 80, "BSW", (("SO", "4", 80),))
    f = compute_features(gdf_from([sq(50.7, 17.9), sq(50.8, 17.9)], [base, withp]), S)
    assert f.loc[0, "h_podgrzybek"] != f.loc[1, "h_podgrzybek"]
    assert f.loc[1, "h_podgrzybek"] == 90


def test_missing_ages_do_not_crash():
    st = Stand("SO", ("BRZ",), None, "BSW", (("BRZ", "", None),))
    f = compute_features(gdf_from([sq(50.7, 17.9)], [st]), S)
    assert f.loc[0, "h_podgrzybek"] == 50


def test_tile_key_bounds():
    assert tile_key(50.0, 17.0) == "50.0_17.0"
    assert tile_key(50.49999, 17.49999) == "50.0_17.0"
    assert tile_key(50.5, 17.5) == "50.5_17.5"
    assert tile_key(50.99, 18.2) == "50.5_18.0"
    assert tile_key(-0.1, -0.6) == "-0.5_-1.0"
    assert tile_key(-0.5, -0.0) == "-0.5_0.0"
    assert tile_key(0.0, 0.25) == "0.0_0.0"


def test_centroid_tiles_split_and_index(tmp_path):
    geoms = [sq(50.2, 17.2), sq(50.3, 17.4), sq(50.6, 17.2), sq(51.1, 18.6)]
    f = compute_features(gdf_from(geoms), S)
    old = tmp_path / "49.0_17.0.json"
    old.write_text("{}")
    idx = write_centroid_tiles(f, KEYS, tmp_path)
    assert idx == {"tile": 0.5, "species": KEYS, "extra": ["wet"],
                   "tiles": ["50.0_17.0", "50.5_17.0", "51.0_18.5"]}
    assert json.load(open(tmp_path / "index.json")) == idx
    assert not old.exists()
    rows = {t: json.load(open(tmp_path / f"{t}.json"))["rows"] for t in idx["tiles"]}
    assert [r[0] for r in rows["50.0_17.0"]] == ["id0", "id1"]
    assert [r[0] for r in rows["50.5_17.0"]] == ["id2"]
    assert [r[0] for r in rows["51.0_18.5"]] == ["id3"]
    for t, rs in rows.items():
        for r in rs:
            assert tile_key(r[1], r[2]) == t and len(r) == 4 + len(KEYS) + 1


def test_centroid_tiles_empty(tmp_path):
    f = compute_features(gdf_from([sq(50.2, 17.2)], [Stand("OL", (), 60, "OL")]), S)
    idx = write_centroid_tiles(f, KEYS, tmp_path)
    assert idx["tiles"] == [] and sorted(p.name for p in tmp_path.iterdir()) == ["index.json"]


def test_compute_features_passes_new_fields():
    import dataclasses
    from forecast.species import Ramp
    sp = {"kurka": dataclasses.replace(S["kurka"], factors={"veg": {"ZAD": 0.7}})}
    g = gdf_from([sq(50.2, 17.2), sq(50.3, 17.3)], [Stand("SO", (), 60, "BSW")] * 2)
    g["veg"] = ["ZAD", None]
    f = compute_features(g, sp)
    assert list(f["h_kurka"]) == [70, 100]


def test_geojsonseq_omits_zero_h(tmp_path):
    g = compute_features(gdf_from([sq(50.2, 17.2)], [Stand("BRZ", (), 30, "BMW")]), S)
    path = tmp_path / "x.geojsonseq"
    write_geojsonseq(g, KEYS, path)
    props = json.loads(path.read_text(encoding="utf-8").splitlines()[0])["properties"]
    assert props.get("h_kozlarz", 0) > 0
    assert "h_borowik" not in props  # brzoza: borowik 0 -> atrybut pominięty


def test_parkings_seq_minzoom(tmp_path):
    from pipeline.build_tiles import write_parkings_seq
    gdf = gpd.GeoDataFrame(
        {"osm": ["n1", "n2", "w3"], "name": ["Leśny", None, "Droga"],
         "fee": ["yes", "no", None]},
        geometry=[Point(17.0, 50.0), Point(17.1, 50.1), Point(17.2, 50.2)],
        crs=4326,
    )
    p = tmp_path / "parkingi.seq"
    write_parkings_seq(gdf, p)
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    for i, line in enumerate(lines):
        obj = json.loads(line)
        assert obj["tippecanoe"] == {"minzoom": 11}
        assert obj["properties"]["osm"] == gdf.iloc[i]["osm"]
        assert ("name" in obj["properties"]) == (not pd.isna(gdf.iloc[i]["name"]))
        assert ("fee" in obj["properties"]) == (not pd.isna(gdf.iloc[i]["fee"]))


from pipeline.build_tiles import weakest_factor


def test_weakest_factor():
    assert weakest_factor({"partner": 0.2, "habitat": 1.0, "veg": 0.7, "age": 0.9}) == "veg"
    assert weakest_factor({"partner": 0.2, "habitat": 1.0, "veg": 0.8}) is None
    assert weakest_factor({"habitat": 1.0, "moist": 0.7, "veg": 0.7}) == "veg"  # remis: kolejność HABITAT_FACTORS


def test_hl_written_only_above_min_h(tmp_path):
    import dataclasses
    sp = {"kurka": dataclasses.replace(S["kurka"], factors={"veg": {"ZAD": 0.7}})}
    g = gdf_from([sq(50.2, 17.2), sq(50.3, 17.3), sq(50.4, 17.4)],
                 [Stand("SO", (), 60, "BSW"), Stand("SO", (), 60, "BSW"), Stand("BRZ", ("SO",), 60, "BSW",
                                                                            (("SO", "PJD", 60),))])
    g["veg"] = ["ZAD", None, "ZAD"]
    f = compute_features(g, sp)
    path = tmp_path / "x.geojsonseq"
    write_geojsonseq(f, ["kurka"], path)
    props = [json.loads(l)["properties"] for l in path.read_text(encoding="utf-8").splitlines()]
    assert props[0]["h_kurka"] == 70 and props[0]["hl_kurka"] == "veg"
    assert "hl_kurka" not in props[1]                       # brak słabej strony
    assert props[2]["h_kurka"] == 14 and "hl_kurka" not in props[2]  # h < 20 -> bez hl_


def test_hl_ignores_age_of_non_partner_dominant():
    # borowik przez domieszkę sosny; panująca brzoza 5 lat nie jest partnerem -> wiek nie jest „słabą stroną”
    g = gdf_from([sq(50.2, 17.2)], [Stand("BRZ", ("SO",), 5, "BSW", (("SO", "4", 80),))])
    f = compute_features(g, S)
    assert f.loc[0, "h_borowik"] >= 20 and f.loc[0, "hl_borowik"] is None


# --- wilgotność miejsca (spec L) ---

def test_wet_in_tiles_and_centroids(tmp_path):
    f = compute_features(gdf_from([sq(50.7, 17.9), sq(50.7, 17.95)]), S)
    f["wet"] = pd.array([82, None], dtype="Int64")
    f["wl"] = pd.Series(["water", None], dtype=object).values
    rows = centroid_rows(f, list(S))
    assert rows[0][-1] == 82 and rows[1][-1] is None
    seq = tmp_path / "l.geojsonseq"
    write_geojsonseq(f, list(S), seq)
    props = [json.loads(l)["properties"] for l in seq.read_text().splitlines()]
    assert props[0]["wet"] == 82 and props[0]["wl"] == "water"
    assert "wet" not in props[1] and "wl" not in props[1]
