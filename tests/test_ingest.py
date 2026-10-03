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
    assert tz["sub_area"].tolist() == ["1.91", "0.78", "0.50", "2.00"]


def test_ingest_tables_and_stats(tmp_path):
    make_pkg(tmp_path)
    stats, db, pq, outline = run_ingest(tmp_path, tmp_path)
    assert stats["02-99"]["name"] == "Testowo"
    assert stats["02-99"]["d_stan"] == 3
    con = duckdb.connect(str(db), read_only=True)
    assert con.execute("select prefix, name, source, cast(produced_at as varchar) from district").fetchall() \
        == [("02-99", "Testowo", "package", "2026-06-23")]
    assert con.execute("select count(*) from subarea where prefix = '02-99'").fetchone()[0] == 4
    assert con.execute("select count(*) from storey_species").fetchone()[0] == 9
    assert con.execute("select count(*) from arod_storey").fetchone()[0] == 3
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
    assert con.execute("select count(*) from subarea").fetchone()[0] == 4
    con.close()


def test_load_stands_columns_filter_and_partners(tmp_path):
    make_pkg(tmp_path)
    _, db, pq, _ = run_ingest(tmp_path, tmp_path)
    g = load_stands(db, pq)
    assert list(g.columns) == ["id", "sp_main", "sp_admix", "partners", "age", "hab", "fun",
                               "prefix", "geometry"]
    assert g.crs.to_epsg() == 4326
    by = g.set_index("id")
    assert set(by.index) == {"02-99-1-01-1-a-00", "02-99-1-01-2-b-00", "02-99-1-01-4-d-00"}

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
    assert "nadleśnictw: 1" in out and "D-STAN: 3" in out
