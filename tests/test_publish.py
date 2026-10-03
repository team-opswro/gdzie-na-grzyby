import gzip
import json
from datetime import datetime, timezone

import pytest

from pipeline import publish

BUILD = "20261003-1530-abc1234"
IMM = "public, max-age=31536000, immutable"


class Stub:
    def __init__(self, prefixes=()):
        self.calls = []
        self.prefixes = list(prefixes)
        self.bodies = {}
        self.deleted = []

    def put_object(self, **kw):
        self.calls.append(("put", kw["Key"]))
        self.bodies[kw["Key"]] = kw

    def upload_file(self, Filename, Bucket, Key, ExtraArgs=None, Config=None):
        self.calls.append(("upload", Key))
        self.bodies[Key] = {"ExtraArgs": ExtraArgs}

    def get_paginator(self, name):
        stub = self
        assert name in ("list_objects_v2",)

        class P:
            def paginate(self, Bucket, Prefix, Delimiter=None):
                if Delimiter:
                    yield {"CommonPrefixes": [{"Prefix": p} for p in stub.prefixes]}
                else:
                    yield {"Contents": [{"Key": Prefix + "a"}, {"Key": Prefix + "b"}]}

        return P()

    def delete_objects(self, Bucket, Delete):
        self.deleted.append([o["Key"] for o in Delete["Objects"]])

    def put_bucket_cors(self, **kw):
        self.calls.append(("cors", kw))


@pytest.fixture
def out(tmp_path):
    (tmp_path / "centroidy").mkdir()
    (tmp_path / "lasy.pmtiles").write_bytes(b"PM")
    for n in ("grid", "nazwy", "gatunki"):
        (tmp_path / f"{n}.json").write_text("{}")
    (tmp_path / "centroidy" / "index.json").write_text("{}")
    (tmp_path / "centroidy" / "49.0_18.5.json").write_text('{"rows": []}')
    (tmp_path / "build.json").write_text(json.dumps({"build": None, "counts": {}}))
    return tmp_path


def test_build_id():
    now = datetime(2026, 10, 3, 15, 30, tzinfo=timezone.utc)
    assert publish.build_id(now, "abc1234") == BUILD


def test_upload_plan_headers(out):
    plan = publish.upload_plan(out, BUILD)
    by_key = {k: (ct, cc) for _, k, ct, cc in plan}
    assert by_key[f"v/{BUILD}/lasy.pmtiles"] == ("application/octet-stream", IMM)
    assert by_key[f"v/{BUILD}/centroidy/49.0_18.5.json"] == ("application/json", IMM)
    assert f"v/{BUILD}/build.json" in by_key
    assert len(plan) == 7
    assert "manifest.json" not in by_key


def test_publish_order_and_manifest_last(out):
    c = Stub()
    publish.publish(c, "b", out, BUILD, 3, now=datetime(2026, 10, 3, 15, 30, tzinfo=timezone.utc))
    assert c.calls[-1] == ("put", "manifest.json")
    assert all(k.startswith(f"v/{BUILD}/") for _, k in c.calls[:-1])
    assert ("upload", f"v/{BUILD}/lasy.pmtiles") in c.calls
    m = c.bodies["manifest.json"]
    assert m["CacheControl"] == "no-cache"
    assert m["ContentEncoding"] == "gzip"
    manifest = json.loads(gzip.decompress(m["Body"]))
    assert manifest["build"] == BUILD and manifest["base"] == f"v/{BUILD}/"
    assert manifest["files"]["centroidy"] == "centroidy/index.json"
    assert manifest["generated_at"] == "2026-10-03T15:30:00Z"


def test_json_gzipped_pmtiles_not(out):
    c = Stub()
    publish.publish(c, "b", out, BUILD, 3)
    g = c.bodies[f"v/{BUILD}/grid.json"]
    assert g["ContentEncoding"] == "gzip" and g["ContentType"] == "application/json"
    assert g["CacheControl"] == IMM
    assert gzip.decompress(g["Body"]) == b"{}"
    extra = c.bodies[f"v/{BUILD}/lasy.pmtiles"]["ExtraArgs"]
    assert "ContentEncoding" not in extra
    assert extra["ContentType"] == "application/octet-stream"
    b = json.loads(gzip.decompress(c.bodies[f"v/{BUILD}/build.json"]["Body"]))
    assert b["build"] == BUILD


def test_keep_deletes_old(out):
    old = [f"v/2026090{i}-1000-aaaaaaa/" for i in range(1, 7)]
    c = Stub(prefixes=old + [f"v/{BUILD}/"])
    publish.publish(c, "b", out, BUILD, 3)
    # kept: BUILD (newest) + 2 newest of the rest... keep=3 newest incl. current
    deleted = {k.split("/")[1] for batch in c.deleted for k in batch}
    assert deleted == {p.split("/")[1] for p in old[:4]}


def test_keep_keeps_current_even_if_old(out):
    c = Stub(prefixes=["v/30000101-0000-zzzzzzz/", "v/30000102-0000-zzzzzzz/", f"v/{BUILD}/"])
    publish.publish(c, "b", out, BUILD, 1)
    deleted = {k.split("/")[1] for batch in c.deleted for k in batch}
    assert BUILD not in deleted
    assert "30000102-0000-zzzzzzz" not in deleted


def test_cors_payload():
    c = Stub()
    publish.set_cors(c, "b", ["https://a", "https://b"])
    rule = c.calls[0][1]["CORSConfiguration"]["CORSRules"][0]
    assert rule["AllowedOrigins"] == ["https://a", "https://b"]
    assert rule["AllowedMethods"] == ["GET", "HEAD"]
    assert rule["AllowedHeaders"] == ["Range", "If-Match", "If-None-Match"]
    assert rule["ExposeHeaders"] == ["ETag", "Content-Range", "Content-Length"]


def test_dry_run_no_credentials(out, capsys, monkeypatch):
    for k in ("S3_ENDPOINT", "S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert publish.main(["--out", str(out), "--dry-run"]) == 0
    txt = capsys.readouterr().out
    assert "lasy.pmtiles" in txt and "manifest.json" in txt
    assert json.loads((out / "build.json").read_text())["build"] is None


def test_missing_env_error(out, monkeypatch, capsys):
    for k in ("S3_ENDPOINT", "S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert publish.main(["--out", str(out)]) != 0
    err = capsys.readouterr().err
    assert "S3_ENDPOINT" in err and "S3_BUCKET" in err


def test_missing_out_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        publish.upload_plan(tmp_path, BUILD)


def test_upload_plan_rejects_unknown_extension(out):
    (out / "sekret.env").write_text("x")
    with pytest.raises(ValueError):
        publish.upload_plan(out, BUILD)


def test_prune_failure_is_warning(out, caplog):
    class Boom(Stub):
        def get_paginator(self, name):
            raise RuntimeError("list failed")

    c = Boom()
    publish.publish(c, "b", out, BUILD, 3)
    assert c.calls[-1] == ("put", "manifest.json")
    assert "sprzatanie" in caplog.text


def test_delete_errors_logged(out, caplog):
    class Err(Stub):
        def delete_objects(self, Bucket, Delete):
            return {"Errors": [{"Key": "v/old/a", "Code": "AccessDenied", "Message": "no"}]}

    c = Err(prefixes=["v/20200101-0000-aaaaaaa/", f"v/{BUILD}/"])
    publish.prune(c, "b", BUILD, 1)
    assert "AccessDenied" in caplog.text


def test_missing_git_clear_message(out, monkeypatch, capsys):
    def nogit(*a, **k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(publish.subprocess, "check_output", nogit)
    assert publish.main(["--out", str(out), "--dry-run"]) == 1
    assert "git" in capsys.readouterr().err


def test_client_checksum_config(monkeypatch):
    for k, v in (("S3_ENDPOINT", "https://e"), ("S3_ACCESS_KEY_ID", "a"),
                 ("S3_SECRET_ACCESS_KEY", "b")):
        monkeypatch.setenv(k, v)
    c = publish._client()
    assert c.meta.config.request_checksum_calculation == "when_required"
    assert c.meta.config.response_checksum_validation == "when_required"


def test_cli_cors_wildcard(out, monkeypatch):
    for k in ("S3_ENDPOINT", "S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(k, "x")
    c = Stub()
    monkeypatch.setattr(publish, "_client", lambda: c)
    assert publish.main(["--out", str(out), "--keep", "0", "--cors", "*"]) == 0
    cors = [kw for name, kw in c.calls if name == "cors"]
    rule = cors[0]["CORSConfiguration"]["CORSRules"][0]
    assert rule["AllowedOrigins"] == ["*"]


def test_cli_cors_denied_is_reported_after_publish(out, monkeypatch, capsys):
    # Token R2 „Object Read & Write” nie może zmieniać CORS bucketu (PutBucketCors -> AccessDenied).
    for k in ("S3_ENDPOINT", "S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(k, "x")

    class Denied(Stub):
        def put_bucket_cors(self, **kw):
            raise RuntimeError("An error occurred (AccessDenied) when calling the PutBucketCors operation")

    c = Denied()
    monkeypatch.setattr(publish, "_client", lambda: c)
    assert publish.main(["--out", str(out), "--keep", "0", "--cors", "*"]) == 3
    assert ("put", "manifest.json") in c.calls
    assert json.loads((out / "build.json").read_text())["build"] is not None
    err = capsys.readouterr().err
    assert "CORS" in err and "AccessDenied" in err
