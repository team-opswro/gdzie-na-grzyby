import os
import time

from forecast.healthcheck import is_fresh


def touch(tmp_path, age_h):
    p = tmp_path / "pogoda.json"
    p.write_text("{}")
    t = time.time() - age_h * 3600
    os.utime(p, (t, t))
    return p


def test_fresh(tmp_path):
    assert is_fresh(touch(tmp_path, age_h=35)) is True


def test_stale(tmp_path):
    assert is_fresh(touch(tmp_path, age_h=37)) is False


def test_missing(tmp_path):
    assert is_fresh(tmp_path / "nope.json") is False


def test_marker_fresh_and_missing(tmp_path, monkeypatch):
    from forecast.healthcheck import marker_path
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    assert is_fresh(marker_path()) is False
    m = tmp_path / "last_upload"
    m.write_text("x")
    assert is_fresh(marker_path()) is True
