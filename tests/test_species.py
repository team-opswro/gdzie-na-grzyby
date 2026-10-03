from forecast.species import load_species


def test_load_species_keys_in_order():
    assert list(load_species()) == ["borowik", "podgrzybek", "kurka", "kozlarz", "maslak", "rydz"]


def test_borowik_values():
    b = load_species()["borowik"]
    assert b.partners == {"SO", "SW", "BK", "DB"} and b.age_max is None
    assert b.temp == (6, 12, 20, 26) and b.season_start == (7, 1) and b.season_end == (10, 31)
    assert b.rain_min == 10 and b.rain_full == 40 and b.soil_moisture_min == 0.15


def test_maslak_age_max():
    assert load_species()["maslak"].age_max == 40


def test_preferred_and_adjacent_disjoint():
    for s in load_species().values():
        assert not (s.habitat_preferred & s.habitat_adjacent)


# --- czynniki siedliska (spec F) ---

import pytest

from forecast.species import Ramp

BASE_SP = """
  x:
    name: X
    partners: [SO]
    age: {min: 10, opt: 20}
    habitat: {preferred: [BSW]}
    season: {start: "07-01", end: "10-31"}
    temp: [6, 12, 20, 26]
"""


def load_yaml(tmp_path, top: str, species_extra: str = ""):
    p = tmp_path / "s.yaml"
    p.write_text(top + "\nspecies:" + BASE_SP + species_extra, encoding="utf-8")
    return load_species(p)


def test_factors_default_inherited(tmp_path):
    s = load_yaml(tmp_path, "factors_default:\n  veg: {ZAD: 0.7}\n")
    assert s["x"].factors["veg"] == {"ZAD": 0.7}


def test_species_override_replaces_table(tmp_path):
    s = load_yaml(tmp_path, "factors_default:\n  degr: {Z1: 0.9, N1: 1.0}\n",
                  "    factors:\n      degr: {}\n")
    assert s["x"].factors["degr"] == {}


def test_ramp_and_bands_parsed(tmp_path):
    s = load_yaml(tmp_path, "factors_default:\n  damage: {full: 40, zero_at: 100, min: 0.6}\n"
                            "  density: [[0.9, 1.0], [0.4, 0.8], [1.0, 0.9]]\n")
    assert s["x"].factors["damage"] == Ramp(40, 100, 0.6)
    assert s["x"].factors["density"] == ((0.4, 0.8), (0.9, 1.0), (1.0, 0.9))


def test_unknown_factor_raises(tmp_path):
    with pytest.raises(ValueError):
        load_yaml(tmp_path, "factors_default:\n  foo: {A: 1.0}\n")


def test_multiplier_out_of_range_raises(tmp_path):
    with pytest.raises(ValueError):
        load_yaml(tmp_path, "factors_default:\n  veg: {ZAD: 1.2}\n")
    with pytest.raises(ValueError):
        load_yaml(tmp_path, "factors_default:\n  damage: {full: 40, zero_at: 100, min: 1.5}\n")


def test_no_factors_section_gives_empty(tmp_path):
    assert load_yaml(tmp_path, "")["x"].factors == {}


def test_repo_species_yaml_loads():
    assert load_species()
