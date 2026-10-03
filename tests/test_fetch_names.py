import json
from pathlib import Path

import duckdb
import pytest

from pipeline import fetch_names
from pipeline.fetch_names import build_names, range_key

FIXTURE = Path(__file__).parent / "fixtures" / "bdl_lesnictwa.json"
DISTRICTS = [{"name": "Brzeg", "prefix": "02-04"}, {"name": "Opole", "prefix": "02-40"}]


def _feats():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["features"]


def test_range_key():
    assert range_key("02-04-1-07-      -    -") == "02-04-1-07"
    assert range_key("13-02-1-03-63    -b   -00") == "13-02-1-03"
    assert range_key("02-04") is None


def test_build_names():
    out = build_names(DISTRICTS, {"02-04": _feats(), "02-40": []})
    assert out["nadl"] == {"02-04": "Brzeg", "02-40": "Opole"}
    assert out["lesn"] == {"02-04-1-07": "Zieleniec", "02-04-1-03": "Lipki"}


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "bdl.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE district (prefix VARCHAR, name VARCHAR, source VARCHAR, "
                "produced_at DATE, package VARCHAR)")
    con.execute("INSERT INTO district VALUES ('02-04','Brzeg','package',NULL,'x'),"
                "('02-40','Opole','package',NULL,'y')")
    con.close()
    return path


def test_main_writes_file(tmp_path, monkeypatch, db):
    monkeypatch.setattr(fetch_names, "_get_json",
                        lambda session, url, params: {"features": _feats()})
    out = tmp_path / "nazwy.json"
    assert fetch_names.main(["--out", str(out), "--db", str(db)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["lesn"]["02-04-1-07"] == "Zieleniec"
    assert data["nadl"] == {"02-04": "Brzeg", "02-40": "Opole"}
    assert not out.with_suffix(".tmp").exists()


def test_main_empty_keeps_existing(tmp_path, monkeypatch, capsys, db):
    monkeypatch.setattr(fetch_names, "_get_json",
                        lambda session, url, params: {"features": []})
    out = tmp_path / "nazwy.json"
    out.write_text("stary", encoding="utf-8")
    assert fetch_names.main(["--out", str(out), "--db", str(db)]) == 1
    assert out.read_text(encoding="utf-8") == "stary"
    assert "Błąd" in capsys.readouterr().err


def test_main_warns_on_empty_district(tmp_path, monkeypatch, capsys, db):
    def fake(session, url, params):
        prefix = params["filter"].split("'")[1].rstrip("%")
        return {"features": _feats() if prefix == "02-04" else []}
    monkeypatch.setattr(fetch_names, "_get_json", fake)
    assert fetch_names.main(["--out", str(tmp_path / "n.json"), "--db", str(db)]) == 0
    err = capsys.readouterr().err
    assert "Ostrzeżenie" in err and "02-40" in err
