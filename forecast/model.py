"""Model pogodowy: dzienny mnożnik w = deszcz × temperatura gleby × sezon."""
from dataclasses import dataclass
from datetime import date

from forecast.species import Species

RAIN_WINDOW = (5, 21)  # dni wstecz, włącznie
RAIN_CORE_WINDOW = (7, 14)
RAIN_CORE_WEIGHT = 1.0
RAIN_EDGE_WEIGHT = 0.5
MOISTURE_LOOKBACK = (1, 3)
MOISTURE_PENALTY = 0.5
MOISTURE_SHALLOW_WEIGHT = 0.5
TEMP_LOOKBACK = (1, 5)
SEASON_RAMP_DAYS = 14
SEASON_FLOOR = 0.1
LIM_THRESHOLD = 0.8
ET_ALPHA = 0.3
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
    return WeatherValues(rain_mm=rain_mm, soil_t=soil_t, soil_m=soil_m, et0_mm=et0_mm, soil_m_deep=soil_m_deep, t2m_min=t2m_min)


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


def soil_moisture_eff(s: DailySeries, i: int) -> float | None:
    """Efektywna wilgotność gleby: ważona średnia z płytkiej i głębokiej warstwy."""
    shallow = _mean_back(s.soil_moisture, i, MOISTURE_LOOKBACK)
    if shallow is None:
        return None
    if s.soil_moisture_deep is None:
        return shallow
    deep = _mean_back(s.soil_moisture_deep, i, MOISTURE_LOOKBACK)
    if deep is None:
        return shallow
    return MOISTURE_SHALLOW_WEIGHT * shallow + (1 - MOISTURE_SHALLOW_WEIGHT) * deep


def _rain_parts(s: DailySeries, i: int, sp: Species) -> tuple[float, bool]:
    """(czynnik opadu, czy zadziałała kara za suchą glebę)."""
    total = water(s, i)
    rain = (total - sp.rain_min) / (sp.rain_full - sp.rain_min)
    rain = min(1.0, max(0.0, rain))
    moisture = soil_moisture_eff(s, i)
    penalized = moisture is not None and moisture < sp.soil_moisture_min
    if penalized:
        rain *= MOISTURE_PENALTY
    return rain, penalized


def rain_factor(s: DailySeries, i: int, sp: Species) -> float:
    return _rain_parts(s, i, sp)[0]


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
    temp = temp_factor(s, i, sp)
    season = season_factor(s.dates[i], sp)
    pulse = pulse_factor(s, i)
    frost = frost_factor(s, i, sp)
    w = min(1.0, rain * temp * season * pulse * frost)
    return WeatherComponents(w=w, rain=rain, temp=temp, season=season, pulse=pulse, frost=frost)


def limiting_factor(
    comps: WeatherComponents, s: DailySeries, i: int, sp: Species
) -> str | None:
    """Kod najsłabszej składowej < LIM_THRESHOLD; remis: season, frost, temp, rain."""
    ordered = [
        ("season", comps.season),
        ("frost", comps.frost),
        ("temp", comps.temp),
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
    return "dry_soil" if _rain_parts(s, i, sp)[1] else "dry"
