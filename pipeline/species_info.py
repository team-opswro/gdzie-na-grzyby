"""Karta gatunku: species.yaml + content/gatunki.yaml -> pipeline/data/out/gatunki.json."""
import argparse
import json
import sys
from pathlib import Path

import yaml

from forecast.species import expand_habitat_list

ROOT = Path(__file__).resolve().parent.parent
SPECIES_PATH = ROOT / "species.yaml"
CONTENT_PATH = ROOT / "content" / "gatunki.yaml"
OUT_PATH = ROOT / "pipeline" / "data" / "out" / "gatunki.json"

MONTHS = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"]
RISKS = {"niejadalny", "trujący", "śmiertelnie trujący"}


def _mmdd(s: str) -> str:
    month, day = s.split("-")
    return f"{int(day)} {MONTHS[int(month) - 1]}"


def format_season(mmdd_start: str, mmdd_end: str) -> str:
    """('07-01', '10-31') -> '1 lip – 31 paź'."""
    return f"{_mmdd(mmdd_start)} – {_mmdd(mmdd_end)}"


def _translate(codes: list[str], table: dict, kind: str, key: str) -> list[str]:
    missing = [c for c in codes if c not in table]
    if missing:
        raise ValueError(f"{key}: brak tłumaczenia kodu {kind}: {', '.join(missing)}")
    return [table[c] for c in codes]


def _groups(species_yaml: dict, content: dict) -> list[dict]:
    """Grupy w kolejności pierwszego wystąpienia w species.yaml; teksty z content/gatunki.yaml."""
    texts = content.get("groups") or {}
    order: dict[str, list[str]] = {}
    for key, sp in species_yaml["species"].items():
        if sp.get("group"):
            order.setdefault(sp["group"], []).append(key)
    missing = set(order) ^ set(texts)
    if missing:
        raise ValueError(f"grupy bez tekstów lub teksty bez grupy: {sorted(missing)}")
    return [{"key": g, "name": texts[g]["name"], "all": texts[g]["all"], "species": keys}
            for g, keys in order.items()]


def build_info(species_yaml: dict, content: dict) -> dict:
    trees = content["codes"]["trees"]
    habitats = content["codes"]["habitats"]
    sets = species_yaml.get("habitat_sets") or {}
    out = []
    for key, sp in species_yaml["species"].items():
        text = content["species"].get(key)
        if text is None:
            raise ValueError(f"brak treści gatunku: {key}")
        for lk in text["lookalikes"]:
            for f in ("name", "latin", "risk", "how"):
                v = lk.get(f)
                if not isinstance(v, str) or not v.strip():
                    raise ValueError(f"{key}: sobowtór bez pola {f}")
            if lk["risk"] not in RISKS:
                raise ValueError(f"{key}: nieznane ryzyko {lk['risk']!r}")
        preferred = expand_habitat_list(sp["habitat"]["preferred"], sets, key)
        adjacent = [c for c in expand_habitat_list(sp["habitat"].get("adjacent", []), sets, key)
                    if c not in preferred]
        out.append({
            "key": key,
            "name": sp["name"],
            "latin": text["latin"],
            "season": {"start": sp["season"]["start"], "end": sp["season"]["end"]},
            "partners": _translate(sp["partners"], trees, "drzewa", key),
            "habitats_preferred": _translate(preferred, habitats, "siedliska", key),
            "habitats_adjacent": _translate(adjacent, habitats, "siedliska", key),
            "age_min": sp["age"]["min"],
            "description": text["description"],
            "lookalikes": [{k: lk[k] for k in ("name", "latin", "risk", "how")}
                           for lk in text["lookalikes"]],
            "wiki": text["wiki"],
            "group": sp.get("group"),
        })
    return {"reviewed": bool(content["reviewed"]), "species": out,
            "groups": _groups(species_yaml, content)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    args = ap.parse_args(argv)
    try:
        species = yaml.safe_load(SPECIES_PATH.read_text(encoding="utf-8"))
        content = yaml.safe_load(CONTENT_PATH.read_text(encoding="utf-8"))
        info = build_info(species, content)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.out.with_suffix(".tmp")
        tmp.write_text(json.dumps(info, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        tmp.replace(args.out)
    except (KeyError, ValueError, OSError, yaml.YAMLError) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 1
    print(f"gatunki: {len(info['species'])} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
