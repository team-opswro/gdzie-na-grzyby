import pandas as pd
import pytest

from forecast.species import load_species
from pipeline.habitat import (
    HABITAT_FACTORS,
    SHARE_WEIGHT,
    Stand,
    age_factor,
    habitat_components,
    habitat_factor,
    habitat_score,
    normalize_habitat,
    normalize_species_code,
    partner_score,
    stand_from_row,
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


def test_share_weight_table():
    assert SHARE_WEIGHT == {"PJD": 0.2, "MJS": 0.3, "1": 0.5, "2": 0.7, "3": 0.7,
                            **{str(i): 0.9 for i in range(4, 11)}}


def test_admixture_partner_legacy_unknown_share_and_age():
    # sp_admix bez partners: udział nieznany (0.3), wiek nieznany (0.5)
    assert habitat_score(Stand("OL", ("SW",), 60, "LMSW"), S["borowik"]) == pytest.approx(0.15)


def test_admixture_with_share_and_age():
    st = Stand("OL", ("BRZ",), 60, "BMW", (("BRZ", "MJS", 30),))
    assert habitat_score(st, S["kozlarz"]) == pytest.approx(0.3)
    assert partner_score(st, S["kozlarz"]) == pytest.approx(0.3)


def test_admixture_without_age_uses_unknown_factor():
    st = Stand("OL", ("BRZ",), 60, "BMW", (("BRZ", "4", None),))
    assert partner_score(st, S["kozlarz"]) == pytest.approx(0.9 * 0.5)


def test_partner_score_takes_max_of_candidates():
    st = Stand("OL", ("BRZ", "SO"), 60, None, (("BRZ", "MJS", 30), ("SO", "3", 40)))
    assert partner_score(st, S["maslak"]) == pytest.approx(0.7 * age_factor(40, S["maslak"]))
    st2 = Stand("SO", ("BRZ",), 40, None, (("BRZ", "10", 40),))
    assert partner_score(st2, S["maslak"]) == 1.0


@pytest.mark.parametrize("st", [
    Stand("SO", (), 80, "BSW"), Stand("SO", (), 15, "BSW"), Stand("DB", (), None, "LMSW"),
    Stand("OL", (), 60, "OL"), Stand("BK", (), 80, "LGSW"),
])
def test_dominant_partner_matches_old_formula(st):
    for sp in S.values():
        old = (1.0 if st.sp_main in sp.partners else 0.0) * age_factor(st.age, sp) * habitat_factor(st.hab, sp)
        assert habitat_score(st, sp) == pytest.approx(old)


def test_partner_score_levels():
    b = S["borowik"]
    assert partner_score(Stand("SO", (), 50, None), b) == 1.0
    assert partner_score(Stand("OL", ("OS",), 50, None), b) == 0.0


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
    ("LWYZW", "LW"), ("LGW", "LW"), ("LMWYZW", "LMW"), ("BMGSW", "BMSW"), ("BMWYZ", "BMW"), ("BGSW", "BSW"), ("BGW", "BW"),
    ("LMWYZSW", "LMWYZ"), ("LWYZSW", "LWYZS"), ("BMWYZSW", "BMWYZ"), ("BMWYZW", "BMW"),
    ("LMGW", "LMW"), ("BMGW", "BMW"), ("BWG", "BW"), ("BMGB", "BMB"), ("BGB", "BB"),
    ("LMG", "LMGSW"), ("LWYZ", "LWYZS"), ("LG", "LGSW"),
])
def test_upland_habitat_scores_like_lowland_analogue(upland, lowland):
    for sp in S.values():
        assert habitat_factor(upland, sp) == habitat_factor(lowland, sp)


def test_beech_on_upland_site_scores_like_lowland_for_borowik():
    assert habitat_score(Stand("BK", (), 80, "LGSW"), S["borowik"]) == habitat_score(Stand("BK", (), 80, "LSW"), S["borowik"]) == 1.0


@pytest.mark.parametrize("code", ["LL", "LLWYZ", "LLG", "OL", "OLJ", "OLJWYZ", "OLJG", "OLG", "LMB"])
def test_codes_without_equivalent_are_other_habitat(code):
    for sp in S.values():
        assert habitat_factor(code, sp) == 0.2


# --- rejestr czynników (walidacja, spec H §5) ---

def test_components_keys_and_values():
    st = Stand("SO", (), 25, "BMW")
    c = habitat_components(st, S["borowik"])
    assert set(c) == set(HABITAT_FACTORS) == {"partner", "habitat", "age"}
    assert c["habitat"] == pytest.approx(0.6)  # BMW = adjacent dla borowika
    assert c["age"] == 0.0  # 25 < age_min 30


def test_score_unchanged_without_neutral():
    st = Stand("SO", ("BRZ",), 60, "BSW", (("BRZ", "2", 40),))
    for sp in S.values():
        assert habitat_score(st, sp) == partner_score(st, sp) * habitat_factor(st.hab, sp)


def test_neutral_habitat_and_age():
    st = Stand("SO", (), 25, "BMW")
    assert habitat_score(st, S["borowik"], neutral=frozenset({"habitat"})) == 0.0
    assert habitat_score(st, S["borowik"], neutral=frozenset({"age"})) == pytest.approx(0.6)
    assert habitat_score(st, S["borowik"], neutral=frozenset({"age", "habitat"})) == 1.0


def test_neutral_age_admixture_uses_share_weight():
    st = Stand("BRZ", ("SO",), 60, "BSW", (("SO", "2", 10),))
    assert habitat_score(st, S["borowik"], neutral=frozenset({"age"})) == pytest.approx(0.7)


def test_neutral_partner():
    st = Stand("OL", (), 60, "BSW")
    assert habitat_score(st, S["borowik"], neutral=frozenset({"partner"})) == 1.0


def test_stand_from_row_normalizes_nan_ages():
    st = stand_from_row("SO", ["BRZ"], float("nan"), "BSW", [("BRZ", "2", pd.NA)])
    assert st == Stand("SO", ("BRZ",), None, "BSW", (("BRZ", "2", None),))
