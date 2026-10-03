"""docker/web-entrypoint.sh: config.json i fragment nginx z proxy /dane/ w trzech trybach."""
import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "docker" / "web-entrypoint.sh"


RESOLV = "# generated\nsearch example.internal\nnameserver 127.0.0.11\nnameserver 2001:db8::53\noptions ndots:0\n"


def run(tmp_path, resolv=RESOLV, **env):
    cfg = tmp_path / "config.json"
    conf = tmp_path / "dane.d" / "dane.conf"
    rc = tmp_path / "resolv.conf"
    if resolv is not None:
        rc.write_text(resolv)
    e = {"PATH": os.environ["PATH"], "WEB_CONFIG_PATH": str(cfg), "WEB_PROXY_CONF": str(conf),
         "WEB_RESOLV_CONF": str(rc)}
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
    # Nazwa rozwiązywana przy żądaniu (zmienna + resolver), nie raz przy starcie nginx.
    assert 'set $dane_host "pub-abc123.r2.dev";' in c
    assert "rewrite ^/dane/(.*)$ /$1 break;" in c
    assert "proxy_pass https://$dane_host;" in c
    assert "proxy_set_header Host $dane_host;" in c
    assert "proxy_ssl_server_name on;" in c
    assert "proxy_ssl_name $dane_host;" in c
    assert "proxy_ssl_verify on;" in c and "proxy_ssl_verify_depth 3;" in c
    assert "proxy_ssl_trusted_certificate /etc/ssl/certs/ca-certificates.crt;" in c
    assert "resolver 127.0.0.11 [2001:db8::53] valid=300s ipv6=off;" in c
    assert "resolver_timeout 5s;" in c
    assert "proxy_max_temp_file_size 0;" in c
    assert "limit_except GET { deny all; }" in c
    assert "gzip off;" in c
    assert "proxy_hide_header Set-Cookie;" in c
    assert "proxy_connect_timeout 5s;" in c and "proxy_read_timeout 30s;" in c
    assert "\\$" not in c  # $ zmiennych nginx nie zostaje escapowany w wyniku


@pytest.mark.parametrize("resolv", [None, "", "# brak serwerów\nsearch x\n", "nameserver bad;host\n"])
def test_proxy_mode_resolver_fallback(tmp_path, resolv):
    r, cfg, conf = run(tmp_path, resolv=resolv, DATA_BASE_URL="https://pub-abc123.r2.dev")
    assert r.returncode == 0, r.stderr
    assert "resolver 1.1.1.1 8.8.8.8 valid=300s ipv6=off;" in conf.read_text()


def test_proxy_mode_with_path_keeps_trailing_slash(tmp_path):
    r, cfg, conf = run(tmp_path, DATA_BASE_URL="https://dane.example.pl/grzyby/v_1", DATA_DIRECT="0")
    assert r.returncode == 0, r.stderr
    assert json.loads(cfg.read_text()) == {"dataBase": "/dane/"}
    c = conf.read_text()
    assert "rewrite ^/dane/(.*)$ /grzyby/v_1/$1 break;" in c
    assert 'set $dane_host "dane.example.pl";' in c


def test_direct_mode(tmp_path):
    r, cfg, conf = run(tmp_path, DATA_BASE_URL="https://pub-abc123.r2.dev", DATA_DIRECT="1")
    assert r.returncode == 0, r.stderr
    assert json.loads(cfg.read_text()) == {"dataBase": "https://pub-abc123.r2.dev/"}
    assert not conf.exists()


@pytest.mark.parametrize("url", ["http://pub-abc123.r2.dev/", "pub-abc123.r2.dev", "javascript:alert(1)//", "https://"])
def test_direct_mode_requires_https(tmp_path, url):
    r, cfg, conf = run(tmp_path, DATA_BASE_URL=url, DATA_DIRECT="1")
    assert r.returncode != 0
    assert "https://" in r.stderr and "DATA_DIRECT=1" in r.stderr
    assert not cfg.exists()
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
