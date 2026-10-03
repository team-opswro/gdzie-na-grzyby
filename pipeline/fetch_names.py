"""Słownik nazw nadleśnictw i leśnictw (BDL OGC API) -> web/data/nazwy.json."""
import argparse
import json
import re
import sys
from pathlib import Path

import requests
import yaml

from pipeline.fetch_bdl import DEFAULT_BASE_URL, FIELDS_YAML, PAGE_LIMIT, ROOT, _get_json

NAMES_PATH = ROOT / "web" / "data" / "nazwy.json"
LAYER = "lesnictwa"


def range_key(adress_forest: str) -> str | None:
    """'02-04-1-07-      -    -' -> '02-04-1-07'; None gdy mniej niż 4 segmenty."""
    parts = re.sub(r"\s+", "", adress_forest or "").split("-")
    if len(parts) < 4 or not all(parts[:4]):
        return None
    return "-".join(parts[:4])


def build_names(districts: list[dict], features_by_prefix: dict[str, list[dict]]) -> dict:
    nadl = {d["prefix"]: d["name"] for d in districts}
    lesn: dict[str, str] = {}
    for prefix in nadl:
        for feat in features_by_prefix.get(prefix, []):
            props = feat.get("properties") or {}
            name = (props.get("forest_range_name") or "").strip()
            key = range_key(props.get("adress_forest") or "")
            if name and key:
                lesn[key] = name
    return {"nadl": nadl, "lesn": lesn}


def fetch_ranges(session, base_url: str, prefix: str) -> list[dict]:
    url = f"{base_url}/collections/{LAYER}/items"
    features: list[dict] = []
    offset = 0
    while True:
        page = _get_json(session, url, {
            "f": "json", "limit": PAGE_LIMIT, "offset": offset,
            "filter": f"adress_forest LIKE '{prefix}%'", "filter-lang": "cql-text",
            "properties": "forest_range_name,adress_forest", "skipGeometry": "true",
        })
        got = page.get("features", [])
        features.extend(got)
        if len(got) < PAGE_LIMIT:
            return features
        offset += PAGE_LIMIT


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=NAMES_PATH)
    args = ap.parse_args(argv)
    try:
        cfg = yaml.safe_load(FIELDS_YAML.read_text(encoding="utf-8"))
        base_url = cfg.get("base_url", DEFAULT_BASE_URL)
        session = requests.Session()
        by_prefix = {}
        for d in cfg["districts"]:
            by_prefix[d["prefix"]] = fetch_ranges(session, base_url, d["prefix"])
            n = len(by_prefix[d["prefix"]])
            if n == 0:
                print(f"Ostrzeżenie: {d['name']} ({d['prefix']}) — 0 leśnictw", file=sys.stderr)
            print(f"{d['name']}: {n} leśnictw")
        names = build_names(cfg["districts"], by_prefix)
        if not names["lesn"]:
            raise ValueError("BDL nie zwróciło żadnych nazw leśnictw")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.out.with_suffix(".tmp")
        tmp.write_text(json.dumps(names, ensure_ascii=False, separators=(",", ":"),
                                  sort_keys=True), encoding="utf-8")
        tmp.replace(args.out)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 1
    print(f"nazwy: {len(names['nadl'])} nadleśnictw, {len(names['lesn'])} leśnictw -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
