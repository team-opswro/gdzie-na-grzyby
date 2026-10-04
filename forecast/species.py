"""Ładowanie reguł gatunków z species.yaml."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, NamedTuple

import yaml

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_RAIN_MIN = 10.0
DEFAULT_RAIN_FULL = 40.0
DEFAULT_SOIL_MOISTURE_MIN = 0.15
DEFAULT_FROST_MIN = -2.0
DEFAULT_WET_GAMMA = 3.0  # siła efektu wilgotności miejsca (spec L); 1.0 = brak efektu

# Czynniki siedliska (spec F): tabele kod -> mnożnik, rampa liczbowa, przedziały liczbowe.
TABLE_FACTORS = ("veg", "moist", "degr", "soil", "twi", "exposure")  # twi/exposure: spec I
RAMP_FACTORS = ("damage",)
BAND_FACTORS = ("density",)
FACTOR_NAMES = TABLE_FACTORS + RAMP_FACTORS + BAND_FACTORS


class Ramp(NamedTuple):
    """1.0 do `full`, liniowo do `min` przy `zero_at`, dalej `min`."""
    full: float
    zero_at: float
    min: float


@dataclass(frozen=True)
class Species:
    key: str
    name: str
    partners: frozenset[str]
    age_min: int
    age_opt: int
    age_max: int | None
    habitat_preferred: frozenset[str]
    habitat_adjacent: frozenset[str]
    season_start: tuple[int, int]  # (miesiąc, dzień)
    season_end: tuple[int, int]
    rain_min: float
    rain_full: float
    soil_moisture_min: float
    frost_min: float
    temp: tuple[float, float, float, float]  # zero_low, opt_low, opt_high, zero_high
    factors: Mapping[str, object] = field(default_factory=dict, hash=False)
    group: str | None = None  # grupa w aplikacji (np. "kozlarze"); None = bez grupy
    # waga partnera (spec L §1b): kod drzewa -> mnożnik 0–1; brak kodu = 1.0
    partner_weights: Mapping[str, float] = field(default_factory=dict, hash=False)
    wet_gamma: float = DEFAULT_WET_GAMMA


def _md(text: str) -> tuple[int, int]:
    month, day = text.split("-")
    return int(month), int(day)


def _mult(key: str, name: str, v) -> float:
    v = float(v)
    if not 0.0 <= v <= 1.0:
        raise ValueError(f"{key}: mnożnik czynnika {name} poza [0, 1]: {v}")
    return v


def _parse_factor(key: str, name: str, raw):
    if name in TABLE_FACTORS:
        return {str(code).upper(): _mult(key, name, v) for code, v in (raw or {}).items()}
    if name in RAMP_FACTORS:
        return Ramp(float(raw["full"]), float(raw["zero_at"]), _mult(key, name, raw["min"]))
    if name in BAND_FACTORS:
        return tuple(sorted((float(hi), _mult(key, name, m)) for hi, m in raw))
    raise ValueError(f"{key}: nieznany czynnik siedliska {name!r}")


def _parse_factors(key: str, raw: dict | None) -> dict[str, object]:
    return {name: _parse_factor(key, name, v) for name, v in (raw or {}).items()}


def expand_habitat_list(items: list[str], sets: Mapping[str, list[str]], key: str = "") -> list[str]:
    """Kody siedlisk w kolejności, bez powtórzeń; "@nazwa" -> kody zestawu z `habitat_sets`."""
    out: list[str] = []
    for it in items:
        if isinstance(it, str) and it.startswith("@"):
            if it[1:] not in sets:
                raise ValueError(f"{key}: nieznany zestaw siedlisk {it!r}")
            codes = sets[it[1:]]
        else:
            codes = [it]
        out += [c for c in codes if c not in out]
    return out


def expand_habitats(items: list[str], sets: Mapping[str, list[str]], key: str = "") -> frozenset[str]:
    return frozenset(expand_habitat_list(items, sets, key))


def _parse(key: str, d: dict, defaults: Mapping[str, object] | None = None,
           sets: Mapping[str, list[str]] | None = None) -> Species:
    temp = tuple(d["temp"])
    if len(temp) != 4:
        raise ValueError(f"{key}: temp musi mieć 4 wartości")
    age, hab, season = d["age"], d["habitat"], d["season"]
    preferred = expand_habitats(hab["preferred"], sets or {}, key)
    # kod w obu listach po rozwinięciu zestawów zostaje preferowany
    adjacent = expand_habitats(hab.get("adjacent", []), sets or {}, key) - preferred
    return Species(
        key=key,
        name=d["name"],
        partners=frozenset(d["partners"]),
        age_min=age["min"],
        age_opt=age["opt"],
        age_max=age.get("max"),
        habitat_preferred=preferred,
        habitat_adjacent=adjacent,
        season_start=_md(season["start"]),
        season_end=_md(season["end"]),
        rain_min=d.get("rain_min", DEFAULT_RAIN_MIN),
        rain_full=d.get("rain_full", DEFAULT_RAIN_FULL),
        soil_moisture_min=d.get("soil_moisture_min", DEFAULT_SOIL_MOISTURE_MIN),
        frost_min=d.get("frost_min", DEFAULT_FROST_MIN),
        temp=temp,
        # nadpisanie gatunkowe zastępuje całą tabelę czynnika
        factors={**(defaults or {}), **_parse_factors(key, d.get("factors"))},
        group=d.get("group"),
        partner_weights={str(c).upper(): _mult(key, "partner_weights", v)
                         for c, v in (d.get("partner_weights") or {}).items()},
        wet_gamma=_wet_gamma(key, d.get("wet_gamma", DEFAULT_WET_GAMMA)),
    )


def _wet_gamma(key: str, v) -> float:
    v = float(v)
    if v < 1.0:
        raise ValueError(f"{key}: wet_gamma musi być ≥ 1 (1 = brak efektu): {v}")
    return v


def load_species(path: Path = ROOT / "species.yaml") -> dict[str, Species]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    defaults = _parse_factors("factors_default", data.get("factors_default"))
    sets = data.get("habitat_sets") or {}
    return {key: _parse(key, d, defaults, sets) for key, d in data["species"].items()}
