import pytest

from forecast.species import load_species
from pipeline.habitat import (
    Stand,
    age_factor,
    habitat_factor,
    habitat_score,
    normalize_habitat,
    normalize_species_code,
    partner_factor,
)

S = load_species()


def test_old_pine_fresh_forest_high_for_podgrzybek():
    assert habitat_score(Stand("SO", (), 80, "BSW"), S["podgrzybek"]) == 1.0


def test_alder_zero_for_all():
    assert all(habitat_score(Stand("OL", (), 60, "OL"), s) == 0 for s in S.values())


def test_young_pine_good_for_maslak_not_borowik():
    st = Stand("SO", (), 15, "BSW")
    assert habitat_score(st, S["maslak"]) == 1.0
    assert habitat_score(st, S["borowik"]) == 0.0


def test_admixture_partner():
    assert habitat_score(Stand("OL", ("SW",), 60, "LMSW"), S["borowik"]) == pytest.approx(0.6)


def test_partner_factor_levels():
    b = S["borowik"]
    assert partner_factor(Stand("SO", (), 50, None), b) == 1.0
    assert partner_factor(Stand("OL", ("SW",), 50, None), b) == 0.6
    assert partner_factor(Stand("OL", ("OS",), 50, None), b) == 0.0


@pytest.mark.parametrize("age,exp", [(40, 0.65), (30, 0.3), (29, 0.0), (None, 0.5)])
def test_age_borowik(age, exp):
    assert age_factor(age, S["borowik"]) == pytest.approx(exp)


@pytest.mark.parametrize("age,exp", [(40, 1.0), (50, 0.65), (60, 0.3), (70, 0.3)])
def test_age_maslak_decline(age, exp):
    assert age_factor(age, S["maslak"]) == pytest.approx(exp)


def test_habitat_levels():
    b = S["borowik"]
    assert (
        habitat_factor("BSW", b),
        habitat_factor("BW", b),
        habitat_factor("OL", b),
        habitat_factor(None, b),
    ) == (1.0, 0.6, 0.2, 1.0)


@pytest.mark.parametrize(
    "raw,exp",
    [
        (" db.s ", "DB"), ("ŚW", "SW"), ("so", "SO"), ("BRZ", "BRZ"),
        ("DB.C", "DB"), ("SO.C", "SO"), ("OL.S", "OL"), ("DB.B", "DB"),
        ("JS", "JS"), ("WZ", "WZ"),
    ],
)
def test_normalize_species(raw, exp):
    assert normalize_species_code(raw) == exp


@pytest.mark.parametrize(
    "raw,exp",
    [
        ("BMśw", "BMSW"), ("  ", None), (None, None), ("", None),
        ("BMŚW", "BMSW"), ("LŁ", "LL"), ("BŚW", "BSW"), ("LMŚW", "LMSW"),
        ("LŚW", "LSW"), ("lł", "LL"), ("BMB", "BMB"), ("OL", "OL"),
    ],
)
def test_normalize_habitat(raw, exp):
    assert normalize_habitat(raw) == exp


@pytest.mark.parametrize("upland,lowland", [
    ("LGSW", "LSW"), ("LWYZS", "LSW"), ("LMWYZ", "LMSW"), ("LMGSW", "LMSW"),
    ("LWYZW", "LW"), ("LGW", "LW"), ("LMWYZW", "LMW"), ("BMGSW", "BMSW"), ("BMWYZ", "BMW"),
])
def test_upland_habitat_scores_like_lowland_analogue(upland, lowland):
    for sp in S.values():
        assert habitat_factor(upland, sp) == habitat_factor(lowland, sp)


def test_beech_on_upland_site_scores_like_lowland_for_borowik():
    assert habitat_score(Stand("BK", (), 80, "LGSW"), S["borowik"]) == habitat_score(Stand("BK", (), 80, "LSW"), S["borowik"]) == 1.0
