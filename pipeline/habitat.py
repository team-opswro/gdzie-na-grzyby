"""Statyczna ocena siedliska h (0-1) dla wydzielenia i gatunku grzyba (spec 4.1)."""
import unicodedata
from dataclasses import dataclass

import pandas as pd

from forecast.species import Species

# Waga udziału domieszki (kod udziału z BDL); nieznany/pusty kod -> SHARE_UNKNOWN.
SHARE_WEIGHT = {"PJD": 0.2, "MJS": 0.3, "1": 0.5, "2": 0.7, "3": 0.7,
                **{str(i): 0.9 for i in range(4, 11)}}
SHARE_UNKNOWN = 0.3
ADJACENT_FACTOR = 0.6
OTHER_HABITAT_FACTOR = 0.2
AGE_MIN_FACTOR = 0.3
AGE_UNKNOWN_FACTOR = 0.5
AGE_DECLINE_YEARS = 20


@dataclass(frozen=True)
class Stand:
    sp_main: str
    sp_admix: tuple[str, ...]
    age: int | None
    hab: str | None
    # (gatunek, kod udziału, wiek|None) domieszek bez gatunku panującego
    partners: tuple = ()


def _ascii_upper(raw: str) -> str:
    # NFKD nie rozkłada Ł/ł, więc zamieniamy je jawnie.
    text = raw.strip().upper().replace("Ł", "L")
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def normalize_species_code(raw: str) -> str:
    return _ascii_upper(raw.split(".")[0])


def normalize_habitat(raw: str | None) -> str | None:
    if raw is None:
        return None
    return _ascii_upper(raw) or None


def age_factor(age: int | None, sp: Species) -> float:
    if age is None:
        return AGE_UNKNOWN_FACTOR
    if age < sp.age_min:
        return 0.0
    if age < sp.age_opt:
        frac = (age - sp.age_min) / (sp.age_opt - sp.age_min)
        return AGE_MIN_FACTOR + (1.0 - AGE_MIN_FACTOR) * frac
    if sp.age_max is None or age <= sp.age_max:
        return 1.0
    over = age - sp.age_max
    if over >= AGE_DECLINE_YEARS:
        return AGE_MIN_FACTOR
    return 1.0 - (1.0 - AGE_MIN_FACTOR) * over / AGE_DECLINE_YEARS


def habitat_factor(hab: str | None, sp: Species) -> float:
    if hab is None:
        return 1.0
    if hab in sp.habitat_preferred:
        return 1.0
    if hab in sp.habitat_adjacent:
        return ADJACENT_FACTOR
    return OTHER_HABITAT_FACTOR


def partner_score(st: Stand, sp: Species, use_age: bool = True) -> float:
    """Ocena partnera: max po gatunku panującym i domieszkach (spec 4.1).
    use_age=False: wiek nie gra roli (ablacja czynnika "age" w walidacji)."""
    af = age_factor if use_age else (lambda _age, _sp: 1.0)
    best = 0.0
    if st.sp_main in sp.partners:
        best = af(st.age, sp)
    # Legacy: sp_admix bez partners -> kod udziału "" (nieznany, 0.3), wiek None.
    partners = st.partners or tuple((c, "", None) for c in st.sp_admix)
    for code, share, age in partners:
        if code in sp.partners:
            w = SHARE_WEIGHT.get((share or "").strip().upper(), SHARE_UNKNOWN)
            best = max(best, w * af(age, sp))
    return best


# Nazwy czynników raportowane przez walidację (pipeline.validate); kolejne specy dopisują swoje.
HABITAT_FACTORS: tuple[str, ...] = ("partner", "habitat", "age")


def habitat_components(st: Stand, sp: Species) -> dict[str, float]:
    """Wartości czynników siedliska; "age" to wiek gatunku panującego (diagnostycznie)."""
    return {
        "partner": partner_score(st, sp),
        "habitat": habitat_factor(st.hab, sp),
        "age": age_factor(st.age, sp),
    }


def habitat_score(st: Stand, sp: Species, neutral: frozenset[str] = frozenset()) -> float:
    """Ocena siedliska 0-1; czynniki z `neutral` liczone jako 1.0 (ablacja)."""
    partner = 1.0 if "partner" in neutral else partner_score(st, sp, use_age="age" not in neutral)
    habitat = 1.0 if "habitat" in neutral else habitat_factor(st.hab, sp)
    return partner * habitat


def _int_or_none(v) -> int | None:
    return None if v is None or pd.isna(v) else int(v)


def stand_from_row(sp_main, sp_admix, age, hab, partners) -> Stand:
    """Stand z wiersza GeoDataFrame (load_stands): NaN/NA -> None, listy -> krotki.
    Wynik jest hashowalny — build_tiles używa go jako klucza cache."""
    return Stand(sp_main, tuple(sp_admix), _int_or_none(age), hab,
                 tuple((c, s, _int_or_none(a)) for c, s, a in partners))
