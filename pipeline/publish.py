"""Publikacja katalogu wyjsciowego builda na S3/R2 (v/<build>/ + manifest.json)."""
import argparse
import gzip
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

IMMUTABLE = "public, max-age=31536000, immutable"
NO_CACHE = "no-cache"
JSON = "application/json"
BINARY = "application/octet-stream"
FILES = {
    "lasy": "lasy.pmtiles",
    "centroidy": "centroidy/index.json",
    "grid": "grid.json",
    "nazwy": "nazwy.json",
    "gatunki": "gatunki.json",
}
ENV = ("S3_ENDPOINT", "S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY")


def build_id(now, git_sha):
    return f"{now.astimezone(timezone.utc):%Y%m%d-%H%M}-{git_sha}"


def upload_plan(out_dir, build):
    """[(lokalna sciezka, klucz, content-type, cache-control)]; brak pliku -> FileNotFoundError."""
    out_dir = Path(out_dir)
    for rel in FILES.values():
        if not (out_dir / rel).is_file():
            raise FileNotFoundError(out_dir / rel)
    paths = [p for p in sorted(out_dir.rglob("*")) if p.is_file()]
    plan = []
    for p in paths:
        rel = p.relative_to(out_dir).as_posix()
        ct = BINARY if p.suffix == ".pmtiles" else JSON
        plan.append((p, f"v/{build}/{rel}", ct, IMMUTABLE))
    return plan


def _gz(data):
    return gzip.compress(data, mtime=0)


def _put_json(client, bucket, key, data, cache):
    client.put_object(
        Bucket=bucket, Key=key, Body=_gz(data), ContentType=JSON,
        ContentEncoding="gzip", CacheControl=cache,
    )


def make_manifest(build, now):
    return {
        "build": build,
        "base": f"v/{build}/",
        "generated_at": f"{now.astimezone(timezone.utc):%Y-%m-%dT%H:%M:%SZ}",
        "files": dict(FILES),
    }


def _build_versions(client, bucket):
    out = []
    for page in client.get_paginator("list_objects_v2").paginate(
        Bucket=bucket, Prefix="v/", Delimiter="/"
    ):
        out += [c["Prefix"].split("/")[1] for c in page.get("CommonPrefixes", [])]
    return out


def prune(client, bucket, current, keep):
    versions = set(_build_versions(client, bucket)) | {current}
    keepers = set(sorted(versions, reverse=True)[:keep]) | {current}
    for v in sorted(versions - keepers):
        keys = []
        for page in client.get_paginator("list_objects_v2").paginate(
            Bucket=bucket, Prefix=f"v/{v}/"
        ):
            keys += [o["Key"] for o in page.get("Contents", [])]
        for i in range(0, len(keys), 1000):
            client.delete_objects(
                Bucket=bucket,
                Delete={"Objects": [{"Key": k} for k in keys[i:i + 1000]], "Quiet": True},
            )


def publish(client, bucket, out_dir, build, keep, now=None, transfer_config=None):
    now = now or datetime.now(timezone.utc)
    for local, key, ct, cc in upload_plan(out_dir, build):
        if local.suffix == ".json":
            data = local.read_bytes()
            if local.name == "build.json" and local.parent == Path(out_dir):
                d = json.loads(data)
                d["build"] = build
                data = json.dumps(d, indent=1).encode()
            _put_json(client, bucket, key, data, cc)
        else:
            client.upload_file(
                str(local), bucket, key,
                ExtraArgs={"ContentType": ct, "CacheControl": cc},
                Config=transfer_config,
            )
    manifest = json.dumps(make_manifest(build, now), indent=1).encode()
    _put_json(client, bucket, "manifest.json", manifest, NO_CACHE)
    if keep:
        prune(client, bucket, build, keep)


def set_cors(client, bucket, origins):
    client.put_bucket_cors(
        Bucket=bucket,
        CORSConfiguration={"CORSRules": [{
            "AllowedOrigins": list(origins),
            "AllowedMethods": ["GET", "HEAD"],
            "AllowedHeaders": ["Range", "If-Match", "If-None-Match"],
            "ExposeHeaders": ["ETag", "Content-Range", "Content-Length"],
            "MaxAgeSeconds": 3600,
        }]},
    )


def _git_sha():
    return subprocess.check_output(
        ["git", "rev-parse", "--short=7", "HEAD"], text=True
    ).strip()


def _client():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT"],
        region_name=os.environ.get("S3_REGION", "auto"),
        aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
        config=Config(s3={"addressing_style": "path"}, signature_version="s3v4"),
    )


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m pipeline.publish")
    ap.add_argument("--out", default="pipeline/data/out")
    ap.add_argument("--keep", type=int, default=3)
    ap.add_argument("--cors", help="origins oddzielone przecinkami")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    now = datetime.now(timezone.utc)
    build = build_id(now, _git_sha())
    try:
        plan = upload_plan(a.out, build)
    except FileNotFoundError as e:
        print(f"brak pliku builda: {e}", file=sys.stderr)
        return 1
    if a.dry_run:
        print(f"build: {build}")
        for local, key, ct, cc in plan:
            print(f"{key}\t{ct}\t{cc}\t{local}")
        print(f"manifest.json\t{JSON}\t{NO_CACHE}")
        print(f"keep: {a.keep}" + (f", cors: {a.cors}" if a.cors else ""))
        return 0

    missing = [k for k in ENV if not os.environ.get(k)]
    if missing:
        print("brak zmiennych srodowiska: " + ", ".join(missing), file=sys.stderr)
        return 2
    from boto3.s3.transfer import TransferConfig

    client, bucket = _client(), os.environ["S3_BUCKET"]
    cfg = TransferConfig(multipart_threshold=16 * 2**20, multipart_chunksize=16 * 2**20)
    publish(client, bucket, a.out, build, a.keep, now=now, transfer_config=cfg)
    if a.cors:
        set_cors(client, bucket, [o.strip() for o in a.cors.split(",") if o.strip()])
    bj = Path(a.out) / "build.json"
    d = json.loads(bj.read_text())
    d["build"] = build
    bj.write_text(json.dumps(d, indent=1))
    print(f"opublikowano {build}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
