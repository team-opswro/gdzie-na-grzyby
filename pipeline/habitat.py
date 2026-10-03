"""Statyczna ocena siedliska h (0-1) dla wydzielenia i gatunku grzyba (spec 4.1)."""
import unicodedata
from dataclasses import dataclass

from forecast.species import Species

ADMIXTURE_FACTOR = 0.6
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


def partner_factor(st: Stand, sp: Species) -> float:
    if st.sp_main in sp.partners:
        return 1.0
    if any(code in sp.partners for code in st.sp_admix):
        return ADMIXTURE_FACTOR
    return 0.0


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


def habitat_score(st: Stand, sp: Species) -> float:
    return partner_factor(st, sp) * age_factor(st.age, sp) * habitat_factor(st.hab, sp)
