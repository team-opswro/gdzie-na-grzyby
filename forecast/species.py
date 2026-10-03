"""Ładowanie reguł gatunków z species.yaml."""
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_RAIN_MIN = 10.0
DEFAULT_RAIN_FULL = 40.0
DEFAULT_SOIL_MOISTURE_MIN = 0.15
DEFAULT_FROST_MIN = -2.0


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


def _md(text: str) -> tuple[int, int]:
    month, day = text.split("-")
    return int(month), int(day)


def _parse(key: str, d: dict) -> Species:
    temp = tuple(d["temp"])
    if len(temp) != 4:
        raise ValueError(f"{key}: temp musi mieć 4 wartości")
    age, hab, season = d["age"], d["habitat"], d["season"]
    return Species(
        key=key,
        name=d["name"],
        partners=frozenset(d["partners"]),
        age_min=age["min"],
        age_opt=age["opt"],
        age_max=age.get("max"),
        habitat_preferred=frozenset(hab["preferred"]),
        habitat_adjacent=frozenset(hab.get("adjacent", [])),
        season_start=_md(season["start"]),
        season_end=_md(season["end"]),
        rain_min=d.get("rain_min", DEFAULT_RAIN_MIN),
        rain_full=d.get("rain_full", DEFAULT_RAIN_FULL),
        soil_moisture_min=d.get("soil_moisture_min", DEFAULT_SOIL_MOISTURE_MIN),
        frost_min=d.get("frost_min", DEFAULT_FROST_MIN),
        temp=temp,
    )


def load_species(path: Path = ROOT / "species.yaml") -> dict[str, Species]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return {key: _parse(key, d) for key, d in data["species"].items()}
