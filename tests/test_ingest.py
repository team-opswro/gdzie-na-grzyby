import shutil
import zipfile
from pathlib import Path

import duckdb
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from pipeline import ingest
from pipeline.ingest import find_packages, load_stands, read_table

FIXTURE = Path(__file__).parent / "fixtures" / "bdl_pkg"
NAME = "BDL_02_99_TESTOWO_2026"

# atrybuty G_SUBAREA (a_i_num, adr_for, area_type, species_cd, spec_age, site_type, forest_fun)
G_ROWS = [
    (299000001, "02-99-1-01-1     -a   -00", "D-STAN", "SO", 80, "LMW", "GOSP"),
    (299000002, "02-99-1-01-2     -b   -00", "D-STAN", "DB.S", 45, "BMŚW", "OCHR"),
    (299000003, "02-99-1-01-3     -c   -00", "ZRĄB", None, 0, "BŚW", "GOSP"),
    (299000004, "02-99-1-01-4     -d   -00", "D-STAN", "BK", 100, "LŁ", "REZ"),
    # wydzielenie wieloczęściowe: dwa obiekty o tym samym a_i_num
    (299000005, "02-99-1-01-5     -f   -00", "D-STAN", "SO", 90, "BMW", "GOSP"),
    (299000005, "02-99-1-01-5     -f   -00", "D-STAN", "SO", 90, "BMW", "GOSP"),
]


def _write_shapes(dest: Path) -> None:
    x0, y0 = 400000, 330000
    g = gpd.GeoDataFrame(
        pd.DataFrame(G_ROWS, columns=["a_i_num", "adr_for", "area_type", "species_cd",
                                      "spec_age", "site_type", "forest_fun"]),
        geometry=[box(x0 + i * 200, y0, x0 + i * 200 + 150, y0 + 150) for i in range(len(G_ROWS))],
        crs=2180,
    )
    g.to_file(dest / "G_SUBAREA.shp")
    gpd.GeoDataFrame({"a_i_num": [299], "i_name": ["Testowo"]},
                     geometry=[box(x0 - 100, y0 - 100, x0 + 1000, y0 + 300)],
                     crs=2180).to_file(dest / "G_INSPECTORATE.shp")


def make_pkg(root: Path, name: str = NAME, *, zipped: bool = True, date: str = "2026-06-23",
             drop: str | None = None) -> Path:
    """Buduje paczkę BDL w `root` (zip z folderem w środku albo katalog)."""
    stage = root / "_stage" / name / name
    stage.mkdir(parents=True)
    for f in FIXTURE.iterdir():
        shutil.copy(f, stage / f.name)
    meta = stage / "metadane.txt"
    meta.write_text(meta.read_text(encoding="utf-8").replace("2026-06-23", date), encoding="utf-8")
    _write_shapes(stage)
    if drop:
        for f in stage.glob(drop):
            f.unlink()
    if not zipped:
        target = root / name
        shutil.move(str(stage), target)
        shutil.rmtree(root / "_stage")
        return target
    target = root / f"{name}.zip"
    with zipfile.ZipFile(target, "w") as zf:
        for f in sorted(stage.iterdir()):
            zf.write(f, f"{name}/{f.name}")
    shutil.rmtree(root / "_stage")
    return target


def run_ingest(tmp_path: Path, pkgs: Path):
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    db, pq, outline = out / "bdl.duckdb", out / "stands.parquet", out / "outline.geojson"
    stats = ingest.ingest(pkgs, db, pq, outline)
    return stats, db, pq, outline


def test_find_packages_picks_latest_production_date(tmp_path):
    make_pkg(tmp_path, date="2026-06-20")
    make_pkg(tmp_path, NAME + "(1)", date="2026-06-23")
    make_pkg(tmp_path, "BDL_13_02_HENRYKOW_2026", date="2026-06-23")
    found = find_packages(tmp_path)
    assert set(found) == {"02-99", "13-02"}
    assert found["02-99"].name == NAME + "(1).zip"


def test_find_packages_tie_prefers_no_suffix_and_zip(tmp_path):
    make_pkg(tmp_path, NAME + "(1)")
    make_pkg(tmp_path, NAME, zipped=False)
    make_pkg(tmp_path, NAME)
    found = find_packages(tmp_path)
    assert found["02-99"].name == NAME + ".zip"


def test_read_table_trims_and_zip_equals_dir(tmp_path):
    z = make_pkg(tmp_path / "z")
    d = make_pkg(tmp_path / "d", zipped=False)
    tz, td = read_table(z, "f_subarea"), read_table(d, "f_subarea.txt")
    pd.testing.assert_frame_equal(tz, td)
    assert tz.loc[0, "area_type_cd"] == "D-STAN"
    assert tz.loc[1, "site_type_cd"] == "BMŚW"
    assert all(isinstance(v, str) for v in tz["arodes_int_num"])
    assert tz["sub_area"].tolist() == ["1.91", "0.78", "0.50", "2.00", "1.00"]


def test_ingest_tables_and_stats(tmp_path):
    make_pkg(tmp_path)
    stats, db, pq, outline = run_ingest(tmp_path, tmp_path)
    assert stats["02-99"]["name"] == "Testowo"
    assert stats["02-99"]["d_stan"] == 4
    assert stats["02-99"]["geometries"] == 5
    con = duckdb.connect(str(db), read_only=True)
    assert con.execute("select prefix, name, source, cast(produced_at as varchar) from district").fetchall() \
        == [("02-99", "Testowo", "package", "2026-06-23")]
    assert con.execute("select count(*) from subarea where prefix = '02-99'").fetchone()[0] == 5
    assert con.execute("select count(*) from storey_species").fetchone()[0] == 12
    assert con.execute("select count(*) from arod_storey").fetchone()[0] == 4
    con.close()
    g = gpd.read_parquet(pq)
    assert list(g.columns) == ["a_i_num", "id", "prefix", "geometry"]
    assert g.crs.to_epsg() == 4326
    assert "02-99-1-01-1-a-00" in set(g["id"])
    o = gpd.read_file(outline)
    assert o["prefix"].tolist() == ["02-99"] and o["name"].tolist() == ["Testowo"]


def test_ingest_is_idempotent(tmp_path):
    make_pkg(tmp_path)
    run_ingest(tmp_path, tmp_path)
    _, db, _, _ = run_ingest(tmp_path, tmp_path)
    con = duckdb.connect(str(db), read_only=True)
    assert con.execute("select count(*) from subarea").fetchone()[0] == 5
    con.close()


def test_load_stands_columns_filter_and_partners(tmp_path):
    make_pkg(tmp_path)
    _, db, pq, _ = run_ingest(tmp_path, tmp_path)
    g = load_stands(db, pq)
    assert list(g.columns) == ["id", "sp_main", "sp_admix", "partners", "age", "hab", "fun",
                               "moist", "degr", "soil", "veg", "damage", "density",
                               "prefix", "geometry"]
    assert g.crs.to_epsg() == 4326
    by = g.set_index("id")
    assert set(by.index) == {"02-99-1-01-1-a-00", "02-99-1-01-2-b-00", "02-99-1-01-4-d-00",
                             "02-99-1-01-5-f-00"}

    s1 = by.loc["02-99-1-01-1-a-00"]
    assert s1["sp_main"] == "SO" and s1["age"] == 80
    assert s1["hab"] == "LMW" and s1["fun"] == "GOSP" and s1["prefix"] == "02-99"
    assert set(s1["partners"]) == {("BRZ", "3", 60), ("DB", "MJS", None), ("SW", "2", 30)}
    assert set(s1["sp_admix"]) == {"BRZ", "DB", "SW"}
    assert isinstance(s1["partners"], tuple) and isinstance(s1["sp_admix"], tuple)

    s4 = by.loc["02-99-1-01-4-d-00"]
    assert s4["sp_main"] == "BK" and s4["age"] == 100
    assert set(s4["partners"]) == {("JD", "4", 40), ("GB", "PJD", 35)}
    assert s4["hab"] == "LL" and s4["fun"] == "REZ"


def test_load_stands_without_composition_uses_g_subarea(tmp_path):
    make_pkg(tmp_path)
    _, db, pq, _ = run_ingest(tmp_path, tmp_path)
    s2 = load_stands(db, pq).set_index("id").loc["02-99-1-01-2-b-00"]
    assert s2["sp_main"] == "DB" and s2["age"] == 45
    assert s2["partners"] == () and s2["sp_admix"] == ()
    assert s2["hab"] == "BMSW"


def test_zip_and_dir_give_same_stands(tmp_path):
    make_pkg(tmp_path / "z")
    make_pkg(tmp_path / "d", zipped=False)
    _, db1, pq1, _ = run_ingest(tmp_path / "z", tmp_path / "z")
    _, db2, pq2, _ = run_ingest(tmp_path / "d", tmp_path / "d")
    a = load_stands(db1, pq1).sort_values("id").reset_index(drop=True)
    b = load_stands(db2, pq2).sort_values("id").reset_index(drop=True)
    pd.testing.assert_frame_equal(a.drop(columns="geometry"), b.drop(columns="geometry"))
    assert a.geometry.geom_equals_exact(b.geometry, 1e-9).all()


def test_missing_file_or_bad_zip_skips_with_warning(tmp_path, capsys):
    make_pkg(tmp_path)
    make_pkg(tmp_path, "BDL_13_02_HENRYKOW_2026", drop="f_storey_species.txt")
    (tmp_path / "BDL_13_03_BOLESLAWIEC_2026.zip").write_bytes(b"not a zip")
    stats, db, pq, _ = run_ingest(tmp_path, tmp_path)
    assert set(stats) == {"02-99"}
    err = capsys.readouterr().err
    assert "13-02" in err and "f_storey_species" in err
    assert "13-03" in err
    assert set(load_stands(db, pq)["prefix"]) == {"02-99"}


def test_cli_fails_when_nothing_ingested(tmp_path, capsys):
    (tmp_path / "pkgs").mkdir()
    make_pkg(tmp_path / "pkgs", drop="G_SUBAREA.*")
    rc = ingest.main(["--packages", str(tmp_path / "pkgs"), "--db", str(tmp_path / "bdl.duckdb"),
                      "--parquet", str(tmp_path / "s.parquet"),
                      "--outline", str(tmp_path / "o.geojson")])
    assert rc != 0
    assert "G_SUBAREA" in capsys.readouterr().err


def test_cli_ok(tmp_path, capsys):
    (tmp_path / "pkgs").mkdir()
    make_pkg(tmp_path / "pkgs")
    rc = ingest.main(["--packages", str(tmp_path / "pkgs"), "--db", str(tmp_path / "bdl.duckdb"),
                      "--parquet", str(tmp_path / "s.parquet"),
                      "--outline", str(tmp_path / "o.geojson")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "nadleśnictw: 1" in out and "D-STAN: 4" in out


def test_partners_exclude_every_row_of_dominant_species(tmp_path):
    # 299000001: SO panujący w DRZEW, SO także w IIP (wiek 40) -> nie jest partnerem
    make_pkg(tmp_path)
    _, db, pq, _ = run_ingest(tmp_path, tmp_path)
    s1 = load_stands(db, pq).set_index("id").loc["02-99-1-01-1-a-00"]
    assert all(p[0] != "SO" for p in s1["partners"])
    assert "SO" not in s1["sp_admix"]


def test_drzew_rank1_wins_over_ip_rank1(tmp_path):
    make_pkg(tmp_path)
    _, db, pq, _ = run_ingest(tmp_path, tmp_path)
    s5 = load_stands(db, pq).set_index("id").loc["02-99-1-01-5-f-00"]
    assert s5["sp_main"] == "SO" and s5["age"] == 90
    assert s5["partners"] == (("MD", "5", 50),)


def test_multipart_stand_dissolved_to_one_geometry(tmp_path):
    make_pkg(tmp_path)
    _, db, pq, _ = run_ingest(tmp_path, tmp_path)
    g = gpd.read_parquet(pq)
    assert not g.duplicated(["prefix", "a_i_num"]).any()
    part = g[g["a_i_num"] == 299000005].to_crs(2180).geometry.iloc[0]
    assert part.area == pytest.approx(2 * 150 * 150, rel=1e-3)
    st = load_stands(db, pq)
    assert (st["id"] == "02-99-1-01-5-f-00").sum() == 1
    con = duckdb.connect(str(db), read_only=True)
    assert con.execute("select count(*) from g_subarea where a_i_num = 299000005").fetchone()[0] == 1
    con.close()


def test_bad_value_skips_package_and_falls_back_to_next_candidate(tmp_path, capsys):
    make_pkg(tmp_path, date="2026-06-20")
    newer = make_pkg(tmp_path, NAME + "(1)", zipped=False, date="2026-06-23")
    sub = newer / "f_subarea.txt"
    sub.write_text(sub.read_text(encoding="utf-8").replace("299000002", "29900000X"),
                   encoding="utf-8")
    stats, db, pq, _ = run_ingest(tmp_path, tmp_path)
    assert stats["02-99"]["package"] == NAME + ".zip"
    assert stats["02-99"]["produced_at"] == "2026-06-20"
    err = capsys.readouterr().err
    assert NAME + "(1)" in err
    con = duckdb.connect(str(db), read_only=True)
    assert con.execute("select count(*) from subarea").fetchone()[0] == 5
    assert con.execute("select package from district").fetchall() == [(NAME + ".zip",)]
    con.close()


def test_missing_file_in_newest_candidate_falls_back(tmp_path, capsys):
    make_pkg(tmp_path, date="2026-06-20")
    make_pkg(tmp_path, NAME + "(1)", date="2026-06-23", drop="f_arod_storey.txt")
    stats, *_ = run_ingest(tmp_path, tmp_path)
    assert stats["02-99"]["package"] == NAME + ".zip"
    assert "f_arod_storey" in capsys.readouterr().err


def test_outputs_written_atomically_no_tmp_left(tmp_path):
    make_pkg(tmp_path)
    _, db, pq, outline = run_ingest(tmp_path, tmp_path)
    run_ingest(tmp_path, tmp_path)
    left = sorted(p.name for p in db.parent.iterdir())
    assert left == sorted([db.name, pq.name, outline.name])


def _api_raw(raw: Path, prefix: str) -> None:
    raw.mkdir(exist_ok=True)
    g = gpd.GeoDataFrame(
        pd.DataFrame({"adr_for": [f"{prefix}-1-01-1     -a   -00", f"{prefix}-1-01-2     -b   -00"],
                      "species_cd": ["SO", "BK"], "spec_age": [60, 90],
                      "site_type": ["BMW", "LMW"], "forest_fun": ["GOSP", "OCHR"],
                      "area_type": ["D-STAN", "D-STAN"]}),
        geometry=[box(20, 51, 20.01, 51.01), box(20.02, 51, 20.03, 51.01)], crs=4326)
    g.to_file(raw / f"{prefix}.geojson", driver="GeoJSON")


def test_api_district_loaded_with_source_api_and_stands(tmp_path):
    make_pkg(tmp_path)
    raw = tmp_path / "raw"
    _api_raw(raw, "06-20")
    db, pq, outline = tmp_path / "o.duckdb", tmp_path / "o.parquet", tmp_path / "o.geojson"
    stats = ingest.ingest(tmp_path, db, pq, outline,
                          [{"name": "Wieluń", "prefix": "06-20"}], raw)
    assert stats["06-20"]["d_stan"] == 2 and stats["06-20"]["source"] == "api"
    con = duckdb.connect(str(db), read_only=True)
    assert con.execute("select source from district where prefix='06-20'").fetchall() == [("api",)]
    assert con.execute("select count(*) from storey_species where prefix='06-20'").fetchone()[0] == 0
    con.close()
    st = load_stands(db, pq)
    api = st[st["prefix"] == "06-20"].set_index("id")
    assert api.loc["06-20-1-01-1-a-00", "sp_main"] == "SO"
    assert api.loc["06-20-1-01-1-a-00", "partners"] == ()
    assert ingest.list_districts(db) == [{"prefix": "02-99", "name": "Testowo"},
                                         {"prefix": "06-20", "name": "Wieluń"}]


def test_package_wins_over_api_district(tmp_path):
    make_pkg(tmp_path)
    raw = tmp_path / "raw"
    _api_raw(raw, "02-99")
    db, pq, outline = tmp_path / "o.duckdb", tmp_path / "o.parquet", tmp_path / "o.geojson"
    stats = ingest.ingest(tmp_path, db, pq, outline, [{"name": "X", "prefix": "02-99"}], raw)
    assert stats["02-99"]["source"] == "package"
    con = duckdb.connect(str(db), read_only=True)
    assert con.execute("select source from district").fetchall() == [("package",)]
    con.close()


def test_api_district_without_raw_file_is_skipped(tmp_path, capsys):
    make_pkg(tmp_path)
    stats = ingest.ingest(tmp_path, tmp_path / "o.duckdb", tmp_path / "o.parquet",
                          tmp_path / "o.geojson", [{"name": "Y", "prefix": "06-20"}],
                          tmp_path / "brak")
    assert "06-20" not in stats and "06-20" in capsys.readouterr().err


def test_load_stands_new_columns(tmp_path):
    make_pkg(tmp_path)
    _, db, pq, _ = run_ingest(tmp_path, tmp_path)
    by = load_stands(db, pq).set_index("id")
    s1 = by.loc["02-99-1-01-1-a-00"]
    assert (s1["moist"], s1["degr"], s1["soil"], s1["veg"]) == ("WW", "Z1", "Bgw", "SZAD")
    assert s1["damage"] == 20 and s1["density"] == pytest.approx(0.6)
    s2 = by.loc["02-99-1-01-2-b-00"]
    assert (s2["moist"], s2["veg"], s2["soil"]) == ("SS", "SCIO", "MRm")


def test_density_from_drzew_before_ip(tmp_path):
    make_pkg(tmp_path)
    _, db, pq, _ = run_ingest(tmp_path, tmp_path)
    assert load_stands(db, pq).set_index("id").loc["02-99-1-01-4-d-00", "density"] == pytest.approx(0.6)


def test_blank_numbers_become_none(tmp_path):
    make_pkg(tmp_path)
    _, db, pq, _ = run_ingest(tmp_path, tmp_path)
    s2 = load_stands(db, pq).set_index("id").loc["02-99-1-01-2-b-00"]
    assert pd.isna(s2["damage"]) and pd.isna(s2["density"])
    s5 = load_stands(db, pq).set_index("id").loc["02-99-1-01-5-f-00"]
    assert pd.isna(s5["moist"]) and pd.isna(s5["veg"])  # brak kodu; stand_from_row -> None
