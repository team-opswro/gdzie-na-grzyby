from forecast.species import load_species


def test_load_species_keys_in_order():
    assert list(load_species()) == ["borowik", "podgrzybek", "kurka", "kozlarz", "maslak", "rydz"]


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
