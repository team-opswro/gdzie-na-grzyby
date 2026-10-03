"""Statyczna ocena siedliska h (0-1) dla wydzielenia i gatunku grzyba (spec 4.1)."""
import unicodedata
from dataclasses import dataclass

import pandas as pd

from forecast.species import BAND_FACTORS, FACTOR_NAMES, RAMP_FACTORS, Species

# Waga udziału domieszki (kod udziału z BDL); nieznany/pusty kod -> SHARE_UNKNOWN.
SHARE_WEIGHT = {"PJD": 0.2, "MJS": 0.3, "1": 0.5, "2": 0.7, "3": 0.7,
                **{str(i): 0.9 for i in range(4, 11)}}
SHARE_UNKNOWN = 0.3
ADJACENT_FACTOR = 0.6
OTHER_HABITAT_FACTOR = 0.2
AGE_MIN_FACTOR = 0.3
AGE_UNKNOWN_FACTOR = 0.5
AGE_DECLINE_YEARS = 20
MOD_FLOOR = 0.4  # modyfikatory (spec F) nie obniżają h poniżej 40% wartości bez nich


@dataclass(frozen=True)
class Stand:
    sp_main: str
    sp_admix: tuple[str, ...]
    age: int | None
    hab: str | None
    # (gatunek, kod udziału, wiek|None) domieszek bez gatunku panującego
    partners: tuple = ()
    # pola BDL dla modyfikatorów (spec F); None = brak danych -> czynnik 1.0
    moist: str | None = None
    degr: str | None = None
    soil: str | None = None  # oryginalna wielkość liter (grupa gleby z wielkich liter)
    veg: str | None = None
    damage: int | None = None
    density: float | None = None


def ascii_code(raw: str) -> str:
    """Kod bez polskich znaków, z zachowaniem wielkości liter ("AUsł" -> "AUsl")."""
    # NFKD nie rozkłada Ł/ł, więc zamieniamy je jawnie.
    text = raw.strip().replace("Ł", "L").replace("ł", "l")
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _ascii_upper(raw: str) -> str:
    return ascii_code(raw.upper())


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


def soil_group(code: str | None) -> str | None:
    """Grupa gleby = wiodące wielkie litery kodu BDL ("BRk" -> "BR", "Bgw" -> "B")."""
    if not code:
        return None
    lead = ""
    for c in code.strip():
        if not c.isupper():
            break
        lead += c
    return lead or None


def factor_value(name: str, st: Stand, sp: Species) -> float:
    """Mnożnik czynnika (spec F §4.3); brak danych lub czynnika w species.yaml -> 1.0."""
    cfg = sp.factors.get(name)
    value = soil_group(st.soil) if name == "soil" else getattr(st, name)
    if cfg is None or value is None:
        return 1.0
    if name in RAMP_FACTORS:
        if value <= cfg.full:
            return 1.0
        if value >= cfg.zero_at:
            return cfg.min
        return 1.0 - (1.0 - cfg.min) * (value - cfg.full) / (cfg.zero_at - cfg.full)
    if name in BAND_FACTORS:
        for upper, mult in cfg:
            if value <= upper:
                return mult
        return cfg[-1][1] if cfg else 1.0
    return cfg.get(value, 1.0)


# Nazwy czynników raportowane przez walidację (pipeline.validate).
HABITAT_FACTORS: tuple[str, ...] = ("partner", "habitat", "age", *FACTOR_NAMES)


def habitat_components(st: Stand, sp: Species) -> dict[str, float]:
    """Wartości czynników siedliska; "age" to wiek gatunku panującego (diagnostycznie)."""
    return {
        "partner": partner_score(st, sp),
        "habitat": habitat_factor(st.hab, sp),
        "age": age_factor(st.age, sp),
        **{name: factor_value(name, st, sp) for name in FACTOR_NAMES},
    }


def habitat_score(st: Stand, sp: Species, neutral: frozenset[str] = frozenset()) -> float:
    """Ocena siedliska 0-1; czynniki z `neutral` liczone jako 1.0 (ablacja)."""
    partner = 1.0 if "partner" in neutral else partner_score(st, sp, use_age="age" not in neutral)
    habitat = 1.0 if "habitat" in neutral else habitat_factor(st.hab, sp)
    mod = 1.0
    for name in FACTOR_NAMES:
        if name not in neutral:
            mod *= factor_value(name, st, sp)
    return partner * habitat * max(MOD_FLOOR, mod)


def _missing(v) -> bool:
    return v is None or (not isinstance(v, str) and pd.isna(v))


def _int_or_none(v) -> int | None:
    return None if _missing(v) else int(v)


def _str_or_none(v) -> str | None:
    return None if _missing(v) or not str(v).strip() else str(v).strip()


def stand_from_row(sp_main, sp_admix, age, hab, partners, *, moist=None, degr=None, soil=None,
                   veg=None, damage=None, density=None) -> Stand:
    """Stand z wiersza GeoDataFrame (load_stands): NaN/NA -> None, listy -> krotki.
    Wynik jest hashowalny — build_tiles używa go jako klucza cache (stąd zaokrąglenia
    uszkodzenia do dziesiątek i zadrzewienia do 0,1 — dane BDL i tak mają taką rozdzielczość)."""
    return Stand(sp_main, tuple(sp_admix), _int_or_none(age), hab,
                 tuple((c, s, _int_or_none(a)) for c, s, a in partners),
                 moist=_str_or_none(moist), degr=_str_or_none(degr), soil=_str_or_none(soil),
                 veg=_str_or_none(veg),
                 damage=None if _missing(damage) else int(round(float(damage), -1)),
                 density=None if _missing(density) else round(float(density), 1))
