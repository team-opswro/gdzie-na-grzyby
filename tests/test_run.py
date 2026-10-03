import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import jsonschema
import pytest

from forecast import run
from forecast.model import DailySeries
from forecast.run import build_payload, main, write_atomic
from forecast.species import ROOT, load_species
from forecast.weather import WeatherError

SCHEMA = json.loads((ROOT / "schema/pogoda.schema.json").read_text())
FIXTURES = ROOT / "tests/fixtures"
TODAY = date(2026, 10, 3)
NOW = datetime(2026, 10, 3, 5, 0, 12, tzinfo=ZoneInfo("Europe/Warsaw"))
SPECIES_KEYS = {"borowik", "podgrzybek", "kurka", "kozlarz", "maslak", "rydz"}
CELLS = [
    {"id": "506_178", "lat": 50.65, "lon": 17.85},
    {"id": "507_178", "lat": 50.75, "lon": 17.85},
]


def make_series(precip: float, start=date(2026, 9, 3), n=37) -> DailySeries:
    return DailySeries(
        dates=[start + timedelta(days=i) for i in range(n)],
        precip=[precip] * n,
        soil_temp=[12.0] * n,
        soil_moisture=[0.3] * n,
    )


def payload(**kw):
    series = {"506_178": make_series(3.0), "507_178": make_series(0.0)}
    return build_payload(CELLS, series, load_species(), TODAY, NOW)


def test_payload_shape_and_days():
    p = payload()
    assert p["days"][0] == "2026-10-03" and len(p["days"]) == 7
    assert p["days"][-1] == "2026-10-09"
    assert p["generated_at"] == "2026-10-03T05:00:12+02:00"
    assert set(p["cells"]["506_178"]) == SPECIES_KEYS
    arr = p["cells"]["506_178"]["borowik"]["w"]
    assert len(arr) == 7 and all(v == round(v, 3) for v in arr)


def test_payload_validates_against_schema():
    jsonschema.validate(payload(), SCHEMA)


def test_wet_cell_differs_from_dry_cell():
    p = payload()
    assert p["cells"]["506_178"]["borowik"]["rain"] != p["cells"]["507_178"]["borowik"]["rain"]


def test_missing_day_raises_value_error():
    series = {"506_178": make_series(1.0, n=30), "507_178": make_series(1.0)}
    with pytest.raises(ValueError):
        build_payload(CELLS, series, load_species(), TODAY, NOW)


def test_shared_fixture_validates():
    data = json.loads((FIXTURES / "pogoda.json").read_text())
    jsonschema.validate(data, SCHEMA)
    assert set(data["cells"]) == {"506_178", "507_178"}
    assert data["days"][0] == "2026-10-03"


def test_schema_rejects_bad_values():
    p = payload()
    p["cells"]["506_178"]["borowik"]["w"][0] = 1.5
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(p, SCHEMA)
    p = payload()
    p["days"] = p["days"][:6]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(p, SCHEMA)


def test_write_atomic_replaces_file(tmp_path):
    out = tmp_path / "pogoda.json"
    out.write_text('{"old": 1}')
    p = payload()
    write_atomic(p, out)
    assert json.loads(out.read_text()) == p
    assert not out.with_suffix(".tmp").exists()


def test_write_atomic_rejects_invalid_and_keeps_old(tmp_path):
    out = tmp_path / "pogoda.json"
    out.write_text('{"old": 1}')
    with pytest.raises(jsonschema.ValidationError):
        write_atomic({"bad": 1}, out)
    assert out.read_text() == '{"old": 1}'
    assert not out.with_suffix(".tmp").exists()


def test_main_writes_output(tmp_path, monkeypatch):
    out = tmp_path / "pogoda.json"
    today = datetime.now(ZoneInfo("Europe/Warsaw")).date()
    series = {
        c["id"]: make_series(2.0, start=today - timedelta(days=30)) for c in CELLS
    }
    monkeypatch.setattr(run, "fetch_series", lambda points, **kw: series)
    assert main(["--grid", str(FIXTURES / "grid.json"), "--out", str(out)]) == 0
    jsonschema.validate(json.loads(out.read_text()), SCHEMA)


def test_main_returns_1_and_keeps_old_on_weather_error(tmp_path, monkeypatch):
    out = tmp_path / "pogoda.json"
    out.write_text('{"old": 1}')

    def boom(points, **kw):
        raise WeatherError("x")

    monkeypatch.setattr(run, "fetch_series", boom)
    assert main(["--grid", str(FIXTURES / "grid.json"), "--out", str(out)]) == 1
    assert out.read_text() == '{"old": 1}'


def test_main_returns_1_on_missing_days(tmp_path, monkeypatch):
    out = tmp_path / "pogoda.json"
    out.write_text('{"old": 1}')
    series = {c["id"]: make_series(1.0, start=date(2020, 1, 1)) for c in CELLS}
    monkeypatch.setattr(run, "fetch_series", lambda points, **kw: series)
    assert main(["--grid", str(FIXTURES / "grid.json"), "--out", str(out)]) == 1
    assert out.read_text() == '{"old": 1}'


def test_main_returns_1_on_missing_grid_file(tmp_path, caplog):
    out = tmp_path / "pogoda.json"
    assert run.main(["--grid", str(tmp_path / "nope.json"), "--out", str(out)]) == 1
    assert not out.exists()
    assert "nieoczekiwany błąd" in caplog.text
