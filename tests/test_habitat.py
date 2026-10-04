import dataclasses

import pandas as pd
import pytest

from tests.generic_species import generic_species
from forecast.species import ROOT, Ramp, load_species
from pipeline.habitat import (
    HABITAT_FACTORS,
    MOD_FLOOR,
    SHARE_WEIGHT,
    Stand,
    age_factor,
    habitat_components,
    habitat_factor,
    factor_value,
    habitat_score,
    normalize_habitat,
    normalize_species_code,
    partner_score,
    soil_group,
    stand_from_row,
)

S = generic_species()


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
    assert set(c) == set(HABITAT_FACTORS) and {"partner", "habitat", "age"} <= set(c)
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


# --- modyfikatory siedliska (spec F) ---

FACT = {
    "veg": {"ZAD": 0.7, "ZIEL": 0.8},
    "moist": {"BO": 0.4},
    "degr": {"Z1": 0.9},
    "soil": {"BR": 0.85},
    "damage": Ramp(40, 100, 0.6),
    "density": ((0.4, 0.8), (0.9, 1.0), (1.0, 0.9)),
}
KURKA = dataclasses.replace(S["kurka"], factors=FACT)
BASE = dict(sp_main="SO", sp_admix=(), age=60, hab="BSW")


def st(**kw):
    return Stand(**{**BASE, **kw})


def test_old_stand_unchanged():
    for sp in S.values():
        assert habitat_score(Stand("SO", (), 80, "BSW"), sp) == \
            partner_score(Stand("SO", (), 80, "BSW"), sp) * habitat_factor("BSW", sp)
    assert habitat_score(st(), KURKA) == 1.0


def test_veg_factor_from_table():
    assert factor_value("veg", st(veg="ZAD"), KURKA) == 0.7
    assert factor_value("veg", st(veg="XYZ"), KURKA) == 1.0
    assert factor_value("veg", st(), KURKA) == 1.0


def test_soil_group():
    assert [soil_group(c) for c in ("BRk", "RDb", "Bgw", "OGw", "MDbr", "Gms", "Pw", None, "")] == \
        ["BR", "RD", "B", "OG", "MD", "G", "P", None, None]
    assert factor_value("soil", st(soil="BRk"), KURKA) == 0.85


def test_damage_ramp():
    vals = [factor_value("damage", st(damage=d), KURKA) for d in (40, 70, 100, 120)]
    assert vals == pytest.approx([1.0, 0.8, 0.6, 0.6])


def test_density_bands():
    vals = [factor_value("density", st(density=d), KURKA) for d in (0.4, 0.6, 1.0, 1.2)]
    assert vals == [0.8, 1.0, 0.9, 0.9]


def test_mod_floor():
    s = st(veg="ZAD", moist="BO", density=0.4)  # 0.7 × 0.4 × 0.8 = 0.224 -> 0.4
    assert MOD_FLOOR == 0.4
    assert habitat_score(s, KURKA) == pytest.approx(0.4)


def test_neutral_factor_only_affects_that_factor():
    s = st(veg="ZAD", moist="BO")
    assert habitat_score(s, KURKA, neutral=frozenset({"veg"})) == pytest.approx(0.4)
    assert habitat_score(s, KURKA, neutral=frozenset({"moist"})) == pytest.approx(0.7)


def test_components_include_all_factors():
    c = habitat_components(st(veg="ZAD"), KURKA)
    assert set(c) == set(HABITAT_FACTORS) and c["veg"] == 0.7


def test_stand_from_row_rounds_damage_and_density():
    s = stand_from_row("SO", [], 60, "BSW", [], damage=23, density=0.94, veg=float("nan"))
    assert (s.damage, s.density, s.veg) == (20, 0.9, None)


def test_kurka_brown_soil_lower_than_podzol():
    k = S["kurka"]
    assert habitat_score(st(soil="BRk"), k) < habitat_score(st(soil="Bw"), k)


# --- nowe gatunki (spec K) ---

def test_aspen_on_lmsw_good_for_red_bolete():
    assert habitat_score(Stand("OS", (), 40, "LMSW"), S["kozlarz_czerwony"]) >= 0.9
    assert habitat_score(Stand("SO", (), 40, "BSW"), S["kozlarz_czerwony"]) == 0


def test_larch_only_for_larch_bolete():
    assert habitat_score(Stand("MD", (), 30, "LMSW"), S["maslak_zolty"]) > 0
    assert habitat_score(Stand("SO", (), 30, "LMSW"), S["maslak_zolty"]) == 0


def test_spruce_rydz_vs_pine_rydz():
    st = Stand("SW", (), 30, "BMSW")
    assert habitat_score(st, S["rydz_swierkowy"]) > 0 and habitat_score(st, S["rydz"]) == 0


def test_existing_species_scores_unchanged():
    cases = [
        (Stand("SO", (), 80, "BSW"), [1.0, 1.0, 1.0, 0.0, 0.3]),
        (Stand("SO", ("BRZ",), 40, "BMW", (("BRZ", "3", 40),)), [0.39, 1.0, 0.6, 0.7, 0.2]),
        (Stand("BK", (), 90, "LSW"), [1.0, 0.0, 0.2, 0.0, 0.0]),
        (Stand("DB", ("SO",), 60, "LMSW", (("SO", "2", 60),)), [1.0, 0.42, 0.6, 0.0, 0.042]),
        (Stand("BRZ", (), 25, "BMW", (), moist="WW", veg="ZAD"), [0.0, 0.0, 0.0, 0.7, 0.0]),
    ]
    for st, want in cases:
        got = [round(habitat_score(st, S[k]), 4)
               for k in ("borowik", "podgrzybek", "kurka", "kozlarz", "maslak")]
        assert got == want


# --- teren (spec I) ---

def test_twi_factor_kozlarz_dry():
    st_dry = Stand("BRZ", (), 30, "BMW", twi_class="DRY")
    assert factor_value("twi", st_dry, S["kozlarz"]) == 0.85
    assert factor_value("twi", st_dry, S["borowik"]) == 1.0
    assert factor_value("twi", Stand("SO", (), 60, "BSW", twi_class="WET"), S["kurka"]) == 0.85


def test_exposure_factor_all_species():
    st_s = Stand("SO", (), 60, "BSW", exposure="S_STEEP")
    assert all(factor_value("exposure", st_s, sp) == 0.85 for sp in S.values())
    assert factor_value("exposure", Stand("SO", (), 60, "BSW", exposure="OTHER"), S["kurka"]) == 1.0
    assert factor_value("exposure", Stand("SO", (), 60, "BSW"), S["kurka"]) == 1.0


# --- spec L §1b: borowik — dąb, trawa, słońce ---

REPO = load_species()
REPO_YAML = ROOT / "species.yaml"


def test_borowik_prefers_oak_over_pine():
    b = REPO["borowik"]
    assert habitat_score(Stand("DB", (), 80, "LMSW"), b) == 1.0
    assert habitat_score(Stand("SO", (), 80, "LMSW"), b) == pytest.approx(0.85)


def test_partner_weight_applies_to_admixture():
    b = REPO["borowik"]
    st = Stand("BRZ", (), 80, "LMSW", partners=(("DB", "3", 80), ("SO", "4", 80)))
    # dąb 0.7 × 1.0 vs sosna 0.9 × 0.85 -> 0.765
    assert partner_score(st, b) == pytest.approx(0.765)


def test_borowik_no_penalty_for_grass_and_sparse_stand():
    b = REPO["borowik"]
    st = Stand("DB", (), 80, "LMSW", veg="ZAD", density=0.4)
    assert habitat_score(st, b) == 1.0
    assert habitat_score(st, REPO["podgrzybek"]) < 1.0


def test_partner_weights_parsed_and_validated(tmp_path):
    p = tmp_path / "s.yaml"
    base = REPO_YAML.read_text(encoding="utf-8")
    p.write_text(base.replace("partner_weights: {DB: 1.0,", "partner_weights: {DB: 1.5,"), encoding="utf-8")
    with pytest.raises(ValueError):
        load_species(p)
