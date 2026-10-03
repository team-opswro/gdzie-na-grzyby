import json
from pathlib import Path

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


def test_main_writes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_names, "_get_json",
                        lambda session, url, params: {"features": _feats()})
    out = tmp_path / "nazwy.json"
    assert fetch_names.main(["--out", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["lesn"]["02-04-1-07"] == "Zieleniec"
    assert len(data["nadl"]) == 27
    assert not out.with_suffix(".tmp").exists()


def test_main_empty_keeps_existing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fetch_names, "_get_json",
                        lambda session, url, params: {"features": []})
    out = tmp_path / "nazwy.json"
    out.write_text("stary", encoding="utf-8")
    assert fetch_names.main(["--out", str(out)]) == 1
    assert out.read_text(encoding="utf-8") == "stary"
    assert "Błąd" in capsys.readouterr().err
