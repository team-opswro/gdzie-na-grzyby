"""docker/web-entrypoint.sh: config.json i fragment nginx z proxy /dane/ w trzech trybach."""
import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "docker" / "web-entrypoint.sh"


def run(tmp_path, **env):
    cfg = tmp_path / "config.json"
    conf = tmp_path / "dane.d" / "dane.conf"
    e = {"PATH": os.environ["PATH"], "WEB_CONFIG_PATH": str(cfg), "WEB_PROXY_CONF": str(conf)}
    e.update(env)
    r = subprocess.run(["sh", str(SCRIPT)], env=e, capture_output=True, text=True)
    return r, cfg, conf


def test_local_mode_without_url(tmp_path):
    r, cfg, conf = run(tmp_path)
    assert r.returncode == 0, r.stderr
    assert json.loads(cfg.read_text()) == {"dataBase": "data/"}
    assert not conf.exists()


def test_proxy_mode_default(tmp_path):
    r, cfg, conf = run(tmp_path, DATA_BASE_URL="https://pub-abc123.r2.dev")
    assert r.returncode == 0, r.stderr
    assert json.loads(cfg.read_text()) == {"dataBase": "/dane/"}
    c = conf.read_text()
    assert "location ^~ /dane/ {" in c
    assert "proxy_pass https://pub-abc123.r2.dev/;" in c
    assert "proxy_set_header Host pub-abc123.r2.dev;" in c
    assert "proxy_ssl_server_name on;" in c
    assert "proxy_ssl_name pub-abc123.r2.dev;" in c
    assert "limit_except GET { deny all; }" in c
    assert "gzip off;" in c
    assert "proxy_hide_header Set-Cookie;" in c
    assert "proxy_connect_timeout 5s;" in c and "proxy_read_timeout 30s;" in c
    assert "resolver" not in c


def test_proxy_mode_with_path_keeps_trailing_slash(tmp_path):
    r, cfg, conf = run(tmp_path, DATA_BASE_URL="https://dane.example.pl/grzyby/v_1", DATA_DIRECT="0")
    assert r.returncode == 0, r.stderr
    assert json.loads(cfg.read_text()) == {"dataBase": "/dane/"}
    assert "proxy_pass https://dane.example.pl/grzyby/v_1/;" in conf.read_text()


def test_direct_mode(tmp_path):
    r, cfg, conf = run(tmp_path, DATA_BASE_URL="https://pub-abc123.r2.dev", DATA_DIRECT="1")
    assert r.returncode == 0, r.stderr
    assert json.loads(cfg.read_text()) == {"dataBase": "https://pub-abc123.r2.dev/"}
    assert not conf.exists()


def test_stale_proxy_conf_removed_on_restart(tmp_path):
    run(tmp_path, DATA_BASE_URL="https://pub-abc123.r2.dev")
    r, cfg, conf = run(tmp_path)
    assert r.returncode == 0
    assert not conf.exists()


@pytest.mark.parametrize("url", [
    "http://pub-abc123.r2.dev/",
    "https://pub-abc123.r2.dev/a b/",
    "https://pub-abc123.r2.dev/;return 200/",
    "https://pub-abc123.r2.dev/x}/",
    "https://pub-abc123.r2.dev/\nfoo",
    "https://user@pub-abc123.r2.dev/",
    "https://pub-abc123.r2.dev:8443/",
    "https://pub-abc123.r2.dev/?q=1",
    "https:///x/",
    "https://.r2.dev/",
    "ftp://x/",
])
def test_proxy_mode_rejects_bad_url(tmp_path, url):
    r, cfg, conf = run(tmp_path, DATA_BASE_URL=url)
    assert r.returncode != 0
    assert "DATA_BASE_URL" in r.stderr
    assert not conf.exists()
    assert not cfg.exists()
