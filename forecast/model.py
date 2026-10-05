"""Model pogodowy: dzienny mnożnik w = impuls deszczu × wilgotność podłoża × temperatura gleby × sezon."""
from dataclasses import dataclass
from datetime import date

from forecast.species import Species

RAIN_WINDOW = (5, 21)  # dni wstecz, włącznie
RAIN_CORE_WINDOW = (7, 14)
RAIN_CORE_WEIGHT = 1.0
RAIN_EDGE_WEIGHT = 0.5
MOISTURE_LOOKBACK = (1, 3)
TEMP_LOOKBACK = (1, 5)
SEASON_RAMP_DAYS = 14
SEASON_FLOOR = 0.1
LIM_THRESHOLD = 0.8
ET_ALPHA = 0.0  # spec M: parowanie liczy wiadro (moist); rain = czysty impuls opadu
# Wiadro wody podłoża (spec M, FAO-56): pojemność warstwy ~25 cm piasków, ET drzewostanu ≈ 0,8·ET0.
BUCKET_MM = 25.0
BUCKET_KC = 0.8
MOIST_LOW = 0.1  # poniżej: podłoże przesuszone
MOIST_HIGH = 0.5  # od połowy zapasu bez ograniczeń (FAO-56: p ≈ 0,5); 0,7 dawało w suszy prawie samo „brak”
MOIST_FLOOR = 0.1  # > 0, żeby korekta wilgotności miejsca (spec L) mogła podnieść wynik w suszy
DRY_DAY_MM = 1.0  # opad dobowy, od którego dzień nie liczy się do „dni bez deszczu”
PULSE_MAX = 0.2
PULSE_DROP_FULL = 3.0
FROST_FLOOR = 0.2
FROST_RECOVERY_DAYS = 7


@dataclass
class DailySeries:
    dates: list[date]
    precip: list[float]
    soil_temp: list[float]
    soil_moisture: list[float]
    et0: list[float] | None = None
    t2m_min: list[float] | None = None
    soil_moisture_deep: list[float] | None = None


@dataclass
class WeatherComponents:
    w: float
    rain: float
    temp: float
    season: float
    pulse: float
    frost: float
    moist: float = 1.0


def trapezoid(x: float, a: float, b: float, c: float, d: float) -> float:
    if x <= a or x >= d:
        return 0.0
    if x < b:
        return (x - a) / (b - a)
    if x <= c:
        return 1.0
    return (d - x) / (d - c)


def _mean_back(values: list[float], i: int, lookback: tuple[int, int]) -> float | None:
    """Średnia z values[i-hi .. i-lo]; indeksy < 0 pomijane; None gdy brak danych."""
    lo, hi = lookback
    picked = [values[i - k] for k in range(lo, hi + 1) if i - k >= 0]
    return sum(picked) / len(picked) if picked else None


@dataclass
class WeatherValues:
    rain_mm: float
    soil_t: float
    soil_m: float
    et0_mm: float | None = None
    soil_m_deep: float | None = None
    t2m_min: float | None = None
    water: float | None = None  # zapas względny wiadra (0–1); None bez et0
    dry_days: int = 0


def weather_values(s: DailySeries, i: int) -> WeatherValues:
    """Realne (niezaokrąglone) wartości pogody: suma opadu w oknie, średnie gleby, nowe wartości diagnostyczne."""
    rain_mm = sum(
        s.precip[i - k] for k in range(RAIN_WINDOW[0], RAIN_WINDOW[1] + 1) if i - k >= 0
    )
    soil_t = _mean_back(s.soil_temp, i, TEMP_LOOKBACK)
    if soil_t is None:
        soil_t = s.soil_temp[i]
    soil_m = _mean_back(s.soil_moisture, i, MOISTURE_LOOKBACK)
    if soil_m is None:
        soil_m = s.soil_moisture[i]
    et0_mm = None
    if s.et0 is not None:
        et0_mm = sum(s.et0[i - k] for k in range(RAIN_WINDOW[0], RAIN_WINDOW[1] + 1) if i - k >= 0)
    soil_m_deep = None
    if s.soil_moisture_deep is not None:
        soil_m_deep = _mean_back(s.soil_moisture_deep, i, MOISTURE_LOOKBACK)
    t2m_min = None
    if s.t2m_min is not None:
        t2m_min = min(s.t2m_min[i - k] for k in range(FROST_RECOVERY_DAYS + 1) if i - k >= 0)
    return WeatherValues(rain_mm=rain_mm, soil_t=soil_t, soil_m=soil_m, et0_mm=et0_mm, soil_m_deep=soil_m_deep,
                         t2m_min=t2m_min, water=bucket_fraction(s, i), dry_days=dry_days(s, i))


def water(s: DailySeries, i: int) -> float:
    """Ważona suma opadu minus ET_ALPHA razy ważona suma parowania w oknie RAIN_WINDOW."""
    total_precip = 0.0
    total_et0 = 0.0
    for k in range(RAIN_WINDOW[0], RAIN_WINDOW[1] + 1):
        if i - k < 0:
            continue
        core = RAIN_CORE_WINDOW[0] <= k <= RAIN_CORE_WINDOW[1]
        weight = RAIN_CORE_WEIGHT if core else RAIN_EDGE_WEIGHT
        total_precip += weight * s.precip[i - k]
        if s.et0 is not None:
            total_et0 += weight * s.et0[i - k]
    return total_precip - ET_ALPHA * total_et0


def bucket_fraction(s: DailySeries, i: int) -> float | None:
    """Zapas wody podłoża na początek dnia i (0–1): wiadro BUCKET_MM od pełnego na starcie serii; None bez et0."""
    if s.et0 is None:
        return None
    store = BUCKET_MM
    for j in range(i):
        store = min(BUCKET_MM, max(0.0, store + s.precip[j] - BUCKET_KC * s.et0[j]))
    return store / BUCKET_MM


def moist_factor(s: DailySeries, i: int) -> float:
    """Wilgotność podłoża teraz: MOIST_FLOOR przy zapasie ≤ MOIST_LOW, liniowo do 1 przy MOIST_HIGH; bez et0 1.0."""
    f = bucket_fraction(s, i)
    if f is None:
        return 1.0
    x = min(1.0, max(0.0, (f - MOIST_LOW) / (MOIST_HIGH - MOIST_LOW)))
    return MOIST_FLOOR + (1 - MOIST_FLOOR) * x


def dry_days(s: DailySeries, i: int) -> int:
    """Liczba pełnych dni od ostatniego dnia z opadem ≥ DRY_DAY_MM (przed dniem i); cała historia, gdy nie padało."""
    for k in range(1, i + 1):
        if s.precip[i - k] >= DRY_DAY_MM:
            return k - 1
    return i


def rain_factor(s: DailySeries, i: int, sp: Species) -> float:
    """Impuls opadu: ważona suma opadu w oknie RAIN_WINDOW między progami gatunku."""
    rain = (water(s, i) - sp.rain_min) / (sp.rain_full - sp.rain_min)
    return min(1.0, max(0.0, rain))


def temp_factor(s: DailySeries, i: int, sp: Species) -> float:
    mean = _mean_back(s.soil_temp, i, TEMP_LOOKBACK)
    if mean is None:
        mean = s.soil_temp[i]
    return trapezoid(mean, *sp.temp)


def season_factor(day: date, sp: Species) -> float:
    start = date(day.year, *sp.season_start)
    end = date(day.year, *sp.season_end)
    if start <= day <= end:
        return 1.0
    n = (start - day).days if day < start else (day - end).days
    if n >= SEASON_RAMP_DAYS:
        return SEASON_FLOOR
    return SEASON_FLOOR + (1 - SEASON_FLOOR) * (1 - n / SEASON_RAMP_DAYS)


def pulse_factor(s: DailySeries, i: int) -> float:
    """Premia za ochłodzenie gleby: spadek średniej temperatury w dwóch oknach."""
    if i - 14 < 0:
        return 1.0
    early = sum(s.soil_temp[i - k] for k in range(8, 15)) / 7
    late = sum(s.soil_temp[i - k] for k in range(1, 6)) / 5
    drop = early - late
    return 1.0 + PULSE_MAX * min(1.0, max(0.0, drop / PULSE_DROP_FULL))


def frost_factor(s: DailySeries, i: int, sp: Species) -> float:
    """Kara za niedawny przymrozek: liniowy powrót od FROST_FLOOR do 1.0."""
    if s.t2m_min is None:
        return 1.0
    for d in range(FROST_RECOVERY_DAYS + 1):
        idx = i - d
        if idx < 0:
            break
        if s.t2m_min[idx] <= sp.frost_min:
            return FROST_FLOOR + (1 - FROST_FLOOR) * d / FROST_RECOVERY_DAYS
    return 1.0


def weather_multiplier(s: DailySeries, i: int, sp: Species) -> WeatherComponents:
    rain = rain_factor(s, i, sp)
    moist = moist_factor(s, i)
    temp = temp_factor(s, i, sp)
    season = season_factor(s.dates[i], sp)
    pulse = pulse_factor(s, i)
    frost = frost_factor(s, i, sp)
    w = min(1.0, rain * moist * temp * season * pulse * frost)
    return WeatherComponents(w=w, rain=rain, temp=temp, season=season, pulse=pulse, frost=frost, moist=moist)


def limiting_factor(
    comps: WeatherComponents, s: DailySeries, i: int, sp: Species
) -> str | None:
    """Kod najsłabszej składowej < LIM_THRESHOLD; remis: season, frost, temp, moist, rain."""
    ordered = [
        ("season", comps.season),
        ("frost", comps.frost),
        ("temp", comps.temp),
        ("moist", comps.moist),
        ("rain", comps.rain),
    ]
    candidates = [(name, v) for name, v in ordered if v < LIM_THRESHOLD]
    if not candidates:
        return None
    name = min(candidates, key=lambda c: c[1])[0]  # min zachowuje kolejność przy remisie
    if name == "season":
        return "season"
    if name == "frost":
        return "frost"
    if name == "temp":
        return "cold" if weather_values(s, i).soil_t < sp.temp[1] else "hot"
    if name == "moist":
        return "dry_soil"
    return "dry"


# --- wilgotność miejsca (spec L): korekta w per wydzielenie, liczona też w kliencie (web/js/data.js) ---
WET_GAMMA_BASE = 3.0  # = forecast.species.DEFAULT_WET_GAMMA; gatunek może mieć własne wet_gamma
WET_NEUTRAL = 50


def wet_gamma(wet: float | None, base: float = WET_GAMMA_BASE) -> float:
    """γ = base^(1 − 2·wet/100); brak wet -> 1 (bez korekty)."""
    if wet is None:
        return 1.0
    return base ** (1 - 2 * wet / 100)


def wet_adjust(w: float, rain: float | None, wet: float | None, base: float = WET_GAMMA_BASE) -> float:
    """w_eff = min(1, w · rain^(γ−1)); rain ≤ 0 lub brak rain/wet -> w bez zmian."""
    if rain is None or wet is None or rain <= 0:
        return w
    return min(1.0, w * rain ** (wet_gamma(wet, base) - 1))
