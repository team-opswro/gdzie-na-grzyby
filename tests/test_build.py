import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from forecast.species import load_species
from pipeline import build
from pipeline.build_tiles import tile_key
from pipeline.species_info import CONTENT_PATH, SPECIES_PATH, build_info

S = load_species()
KEYS = list(S)


def stands():
    rows = [  # id, sp_main, partners, age, hab, fun, (lat, lon)
        ("a", "SO", (), 80, "BSW", None, (50.2, 17.2)),
        ("b", "DB", (("SO", "4", 80),), 80, "BSW", None, (50.7, 17.9)),
        ("c", "SO", (), 80, "BSW", "REZ", (50.8, 17.9)),
        ("d", "OL", (), 60, "OL", None, (51.1, 18.6)),
    ]
    return gpd.GeoDataFrame(
        {
            "id": [r[0] for r in rows],
            "sp_main": [r[1] for r in rows],
            "sp_admix": pd.Series([tuple(p[0] for p in r[2]) for r in rows], dtype=object).values,
            "partners": pd.Series([r[2] for r in rows], dtype=object).values,
            "age": pd.array([r[3] for r in rows], dtype="Int64"),
            "hab": [r[4] for r in rows],
            "fun": [r[5] for r in rows],
            "prefix": ["02-04"] * len(rows),
        },
        geometry=[box(lo, la, lo + 0.001, la + 0.001) for *_, (la, lo) in rows],
        crs=4326,
    )


RES = gpd.GeoDataFrame({"name": ["X"]}, geometry=[box(10.0, 40.0, 10.1, 40.1)], crs=4326)


class FakeTippecanoe:
    def __init__(self):
        self.cmds = []

    def __call__(self, cmd, check):
        assert check
        self.cmds.append(cmd)
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"PMTiles")


def test_run_writes_out_dir(tmp_path):
    out = tmp_path / "out"
    names = tmp_path / "nazwy_src.json"
    names.write_text('{"nadl": {}, "lesn": {}}', encoding="utf-8")
    tip = FakeTippecanoe()
    meta = build.run(stands(), S, RES, out, tmp_path / "b", names, tippecanoe=tip,
                     now="2026-10-03T12:00:00Z")

    assert (out / "lasy.pmtiles").read_bytes() == b"PMTiles"
    assert len(tip.cmds) == 1 and "lasy:" + str(tmp_path / "b" / "lasy.geojsonseq") in tip.cmds[0]
    idx = json.loads((out / "centroidy" / "index.json").read_text())
    assert idx["tiles"] == [tile_key(50.2, 17.2), tile_key(50.7, 17.9)]
    ids = [r[0] for t in idx["tiles"]
           for r in json.loads((out / "centroidy" / f"{t}.json").read_text())["rows"]]
    assert ids == ["a", "b"]  # c w rezerwacie (flaga REZ), d poniżej progu
    assert len(json.loads((out / "grid.json").read_text())["cells"]) == 4
    assert (out / "nazwy.json").read_text(encoding="utf-8") == names.read_text(encoding="utf-8")
    gat = json.loads((out / "gatunki.json").read_text(encoding="utf-8"))
    import yaml
    assert gat == build_info(yaml.safe_load(SPECIES_PATH.read_text(encoding="utf-8")),
                             yaml.safe_load(CONTENT_PATH.read_text(encoding="utf-8")))
    bj = json.loads((out / "build.json").read_text())
    assert bj == meta
    assert bj["build"] is None and bj["generated_at"] == "2026-10-03T12:00:00Z"
    assert bj["counts"] == {"stands": 4, "with_partners": 1, "rez": 1, "centroids": 2,
                            "centroid_tiles": 2, "grid_cells": 4}
    assert not (out / "centroidy.json").exists()


def test_run_names_already_in_out(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "nazwy.json").write_text("{}", encoding="utf-8")
    build.run(stands(), S, RES, out, tmp_path / "b", out / "nazwy.json",
              tippecanoe=FakeTippecanoe(), now="t")
    assert (out / "nazwy.json").read_text() == "{}"


def test_main_requires_names_and_reserves(tmp_path, capsys):
    res = tmp_path / "r.geojson"
    RES.to_file(res, driver="GeoJSON")
    rc = build.main(["--out", str(tmp_path / "o"), "--reserves", str(res),
                     "--names", str(tmp_path / "missing.json")])
    assert rc == 1 and "fetch_names" in capsys.readouterr().err
    rc = build.main(["--out", str(tmp_path / "o"), "--reserves", str(tmp_path / "nope"),
                     "--names", str(res)])
    assert rc == 1 and "fetch_reserves" in capsys.readouterr().err


def test_main_runs_with_loaded_stands(tmp_path, monkeypatch):
    res = tmp_path / "r.geojson"
    RES.to_file(res, driver="GeoJSON")
    names = tmp_path / "n.json"
    names.write_text("{}")
    seen = {}

    def fake_load(db, pq):
        seen["args"] = (db, pq)
        return stands()
    monkeypatch.setattr(build, "load_stands", fake_load)
    monkeypatch.setattr(build.subprocess, "run", FakeTippecanoe())
    rc = build.main(["--out", str(tmp_path / "o"), "--reserves", str(res), "--names", str(names),
                     "--db", "x.duckdb", "--parquet", "y.parquet", "--build-dir", str(tmp_path / "b")])
    assert rc == 0 and seen["args"] == (Path("x.duckdb"), Path("y.parquet"))
    assert json.loads((tmp_path / "o" / "build.json").read_text())["counts"]["stands"] == 4


def test_defaults_point_to_out():
    from pipeline import fetch_names, species_info
    assert build.DEFAULT_OUT == Path(build.__file__).parent / "data" / "out"
    assert fetch_names.NAMES_PATH == build.DEFAULT_OUT / "nazwy.json"
    assert species_info.OUT_PATH == build.DEFAULT_OUT / "gatunki.json"
