from forecast.species import ROOT, load_species


def test_load_species_keys_in_order():
    keys = list(load_species())
    assert keys[:6] == ["borowik", "podgrzybek", "kurka", "kozlarz", "maslak", "rydz"]
    assert keys[6:] == ["kozlarz_czerwony", "kozlarz_pomaranczowy", "kozlarz_grabowy", "kozlarz_debowy",
                        "borowik_sosnowy", "borowik_usiatkowany", "podgrzybek_zajaczek",
                        "podgrzybek_zlotawy", "podgrzybek_czerwonawy", "maslak_zolty", "maslak_sitarz",
                        "rydz_swierkowy"]


def test_borowik_values():
    b = load_species()["borowik"]
    assert b.partners == {"SO", "SW", "BK", "DB"} and b.age_max is None
    assert b.temp == (6, 12, 20, 26) and b.season_start == (7, 1) and b.season_end == (10, 31)
    assert b.rain_min == 10 and b.rain_full == 40 and b.soil_moisture_min == 0.15
    assert b.frost_min == -2.0


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


def test_yaml_factor_values():
    s = load_species()
    assert all(sp.factors["moist"] == {} for sp in s.values())  # zneutralizowany po walidacji
    assert s["rydz"].factors["degr"] == {} and s["maslak"].factors["degr"] == {}
    assert s["kozlarz"].factors["soil"] == {"B": 0.9, "RD": 0.9}
    assert s["podgrzybek"].factors["veg"] == {"ZAD": 0.7, "ZIEL": 0.8, "SZAD": 0.9}
    # spec L §1b: borowik bez kary za runo i rzadki drzewostan, dąb premiowany
    assert s["borowik"].factors["veg"] == {}
    assert s["borowik"].factors["density"] == ((0.9, 1.0), (1.0, 0.9))
    assert s["borowik"].partner_weights == {"DB": 1.0, "BK": 0.9, "SO": 0.85, "SW": 0.85}
    assert s["podgrzybek"].partner_weights == {}
    # spec L: siła efektu wilgotności miejsca (walidacja GBIF)
    assert s["borowik"].wet_gamma == 1.5 and s["podgrzybek"].wet_gamma == 3.0
    assert s["borowik"].factors["damage"] == Ramp(40, 100, 0.6)


# --- zestawy siedlisk i grupy (spec K) ---

SETS = "habitat_sets:\n  bory_ubogie: [BS, BSW, BGSW]\n  lasy_swieze: [LSW]\n"


def test_habitat_set_expansion(tmp_path):
    extra = """  y:
    name: Y
    partners: [SO]
    age: {min: 10, opt: 20}
    habitat: {preferred: ["@bory_ubogie", LMSW], adjacent: ["@lasy_swieze", BSW]}
    season: {start: "07-01", end: "10-31"}
    temp: [6, 12, 20, 26]
    group: testowe
"""
    s = load_yaml(tmp_path, SETS, extra)
    assert s["y"].habitat_preferred == {"BS", "BSW", "BGSW", "LMSW"}
    assert s["y"].habitat_adjacent == {"LSW"}  # BSW zostaje w preferred
    assert s["y"].group == "testowe" and s["x"].group is None


def test_unknown_set_raises(tmp_path):
    extra = BASE_SP.replace("x:", "z:").replace("[BSW]", '["@nie_ma"]')
    with pytest.raises(ValueError):
        load_yaml(tmp_path, SETS, extra)


def test_groups_assigned():
    s = load_species()
    assert s["kozlarz_czerwony"].group == "kozlarze" and s["kozlarz"].group == "kozlarze"
    assert s["kurka"].group is None and s["rydz"].group == "rydze"
    assert {k for k, v in s.items() if v.group == "borowiki"} == {"borowik", "borowik_sosnowy",
                                                                  "borowik_usiatkowany"}


def test_rydz_only_pine():
    s = load_species()
    assert s["rydz"].partners == {"SO"} and s["rydz"].name == "Rydz mleczaj"
    assert s["rydz_swierkowy"].partners == {"SW"}


def test_new_species_values_from_spec():
    s = load_species()
    c = s["kozlarz_czerwony"]
    assert c.partners == {"OS", "TP"} and (c.age_min, c.age_opt) == (10, 20)
    assert c.season_start == (6, 15) and c.temp == (6, 12, 20, 26)
    assert "LMSW" in c.habitat_preferred and "LW" in c.habitat_adjacent
    assert s["maslak_sitarz"].age_max == 60 and s["borowik_usiatkowany"].temp == (10, 15, 23, 28)
    assert s["podgrzybek_zlotawy"].season_end == (11, 15)
    assert s["kozlarz_pomaranczowy"].factors["moist"] == s["kozlarz"].factors["moist"]
    assert s["maslak_sitarz"].factors["moist"] == s["maslak"].factors["moist"]
    assert s["rydz_swierkowy"].factors["degr"] == {}


def test_wet_gamma_below_one_rejected(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text((ROOT / "species.yaml").read_text(encoding="utf-8").replace("wet_gamma: 1.5", "wet_gamma: 0.5"),
                 encoding="utf-8")
    with pytest.raises(ValueError, match="wet_gamma"):
        load_species(p)
