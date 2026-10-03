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
from forecast.weather import RateLimitError, WeatherError

SCHEMA = json.loads((ROOT / "schema/pogoda.schema.json").read_text())
FIXTURES = ROOT / "tests/fixtures"
TODAY = date(2026, 10, 3)
NOW = datetime(2026, 10, 3, 5, 0, 12, tzinfo=ZoneInfo("Europe/Warsaw"))
SPECIES_KEYS = set(load_species())
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
    assert len(p["days"]) == 8
    assert p["days"][0] == "2026-10-02" and p["days"][1] == "2026-10-03"
    assert p["days"][-1] == "2026-10-09"
    assert p["generated_at"] == "2026-10-03T05:00:12+02:00"
    assert set(p["cells"]["506_178"]) == SPECIES_KEYS
    arr = p["cells"]["506_178"]["borowik"]["w"]
    assert len(arr) == 8 and all(v == round(v, 3) for v in arr)


def test_wx_values_and_lim():
    p = payload()
    for cid in ("506_178", "507_178"):
        wx = p["wx"][cid]
        assert set(wx) == {"rain_mm", "soil_t", "soil_m"}
        assert all(len(v) == 8 for v in wx.values())
    assert p["wx"]["506_178"]["rain_mm"][1] == 51.0  # 17 dni * 3,0 mm
    assert p["wx"]["507_178"]["rain_mm"][1] == 0.0
    assert p["wx"]["506_178"]["soil_t"][1] == 12.0
    assert p["wx"]["506_178"]["soil_m"][1] == 0.3
    allowed = {"dry", "dry_soil", "cold", "hot", "season", None}
    for sp in SPECIES_KEYS:
        assert all(v in allowed for v in p["cells"]["507_178"][sp]["lim"])
        assert len(p["cells"]["507_178"][sp]["lim"]) == 8
    assert "dry" in p["cells"]["507_178"]["borowik"]["lim"]


def test_missing_yesterday_raises_value_error():
    series = {c["id"]: make_series(1.0, start=TODAY) for c in CELLS}
    with pytest.raises(ValueError):
        build_payload(CELLS, series, load_species(), TODAY, NOW)


def test_old_v1_fixture_does_not_validate():
    data = json.loads((FIXTURES / "pogoda_v1.json").read_text())
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, SCHEMA)


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
    assert data["days"][0] == "2026-10-02"


def test_schema_rejects_bad_values():
    p = payload()
    p["cells"]["506_178"]["borowik"]["w"][0] = 1.5
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(p, SCHEMA)
    p = payload()
    p["days"] = p["days"][:7]
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


def test_main_rate_limit_aborts_run_logged(tmp_path, monkeypatch, caplog):
    out = tmp_path / "pogoda.json"
    out.write_text('{"old": 1}')

    def limited(points, **kw):
        raise RateLimitError("Open-Meteo: limit żądań (429)")

    monkeypatch.setattr(run, "fetch_series", limited)
    assert main(["--grid", str(FIXTURES / "grid.json"), "--out", str(out)]) == 1
    assert out.read_text() == '{"old": 1}'
    assert "przerwano" in caplog.text and "429" in caplog.text


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


# --- grid z bucketu, upload, znacznik -------------------------------------

import gzip  # noqa: E402


class FakeResp:
    def __init__(self, content, status=200):
        self.content = content
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return json.loads(self.content)


class FakeSession:
    def __init__(self, files):
        self.files = files
        self.urls = []

    def get(self, url, timeout=None):
        self.urls.append(url)
        if url not in self.files:
            return FakeResp(b"", 404)
        return FakeResp(self.files[url])


MANIFEST = {"base": "v/B1/", "files": {"grid": "grid.json"}}
GRID_BYTES = (FIXTURES / "grid.json").read_bytes()


def test_fetch_grid_normalizes_slash_and_reads_manifest():
    s = FakeSession({
        "https://d.example/manifest.json": json.dumps(MANIFEST).encode(),
        "https://d.example/v/B1/grid.json": GRID_BYTES,
    })
    cells = run.fetch_grid("https://d.example", s)
    assert cells == json.loads(GRID_BYTES)["cells"]


def test_fetch_grid_handles_raw_gzip_bytes():
    s = FakeSession({
        "https://d.example/manifest.json": gzip.compress(json.dumps(MANIFEST).encode()),
        "https://d.example/v/B1/grid.json": gzip.compress(GRID_BYTES),
    })
    assert run.fetch_grid("https://d.example/", s) == json.loads(GRID_BYTES)["cells"]


def test_fetch_grid_http_error():
    with pytest.raises(Exception):
        run.fetch_grid("https://d.example/", FakeSession({}))


class StubS3:
    def __init__(self):
        self.puts = []

    def put_object(self, **kw):
        self.puts.append(kw)


def test_upload_pogoda(tmp_path):
    p = tmp_path / "pogoda.json"
    p.write_text('{"a": 1}')
    c = StubS3()
    run.upload_pogoda(c, "bkt", p)
    kw = c.puts[0]
    assert kw["Bucket"] == "bkt" and kw["Key"] == "live/pogoda.json"
    assert kw["ContentType"] == "application/json"
    assert kw["ContentEncoding"] == "gzip"
    assert kw["CacheControl"] == "no-cache"
    assert json.loads(gzip.decompress(kw["Body"])) == {"a": 1}


def _setup_main(tmp_path, monkeypatch, with_env=True):
    today = datetime.now(ZoneInfo("Europe/Warsaw")).date()
    series = {c["id"]: make_series(2.0, start=today - timedelta(days=30)) for c in CELLS}
    monkeypatch.setattr(run, "fetch_series", lambda points, **kw: series)
    monkeypatch.setenv("STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DATA_BASE_URL", "https://d.example")
    monkeypatch.setattr(run, "fetch_grid", lambda url, session: json.loads(GRID_BYTES)["cells"])
    stub = StubS3()
    monkeypatch.setattr(run, "make_client", lambda: stub)
    for k in ("S3_ENDPOINT", "S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"):
        if with_env:
            monkeypatch.setenv(k, "x")
        else:
            monkeypatch.delenv(k, raising=False)
    return stub


def test_main_upload_writes_marker(tmp_path, monkeypatch):
    stub = _setup_main(tmp_path, monkeypatch)
    assert main(["--grid-from-url", "--upload"]) == 0
    assert stub.puts[0]["Key"] == "live/pogoda.json"
    assert (tmp_path / "state" / "last_upload").exists()


def test_main_upload_failure_no_marker(tmp_path, monkeypatch):
    stub = _setup_main(tmp_path, monkeypatch)

    def boom(**kw):
        raise RuntimeError("s3 down")

    stub.put_object = boom
    assert main(["--grid-from-url", "--upload"]) == 1
    assert not (tmp_path / "state" / "last_upload").exists()


def test_main_upload_missing_env(tmp_path, monkeypatch, caplog):
    stub = _setup_main(tmp_path, monkeypatch, with_env=False)
    assert main(["--grid-from-url", "--upload"]) == 1
    assert not stub.puts
    assert not (tmp_path / "state" / "last_upload").exists()
    assert "S3_" in caplog.text


def test_main_no_upload_no_marker(tmp_path, monkeypatch):
    _setup_main(tmp_path, monkeypatch)
    out = tmp_path / "p.json"
    assert main(["--grid-from-url", "--out", str(out)]) == 0
    assert out.exists() and not (tmp_path / "state" / "last_upload").exists()


def test_main_grid_from_url_without_base_url(tmp_path, monkeypatch):
    _setup_main(tmp_path, monkeypatch)
    monkeypatch.delenv("DATA_BASE_URL")
    assert main(["--grid-from-url", "--out", str(tmp_path / "p.json")]) == 1
