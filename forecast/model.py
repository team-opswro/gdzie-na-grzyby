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
TEMP_LOOKBACK = (1, 5)
SEASON_RAMP_DAYS = 14
SEASON_FLOOR = 0.1
LIM_THRESHOLD = 0.8


@dataclass
class DailySeries:
    dates: list[date]
    precip: list[float]
    soil_temp: list[float]
    soil_moisture: list[float]


@dataclass
class WeatherComponents:
    w: float
    rain: float
    temp: float
    season: float


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


def weather_values(s: DailySeries, i: int) -> WeatherValues:
    """Realne (niezaokrąglone) wartości pogody: suma opadu w oknie, średnie gleby."""
    rain_mm = sum(
        s.precip[i - k] for k in range(RAIN_WINDOW[0], RAIN_WINDOW[1] + 1) if i - k >= 0
    )
    soil_t = _mean_back(s.soil_temp, i, TEMP_LOOKBACK)
    if soil_t is None:
        soil_t = s.soil_temp[i]
    soil_m = _mean_back(s.soil_moisture, i, MOISTURE_LOOKBACK)
    if soil_m is None:
        soil_m = s.soil_moisture[i]
    return WeatherValues(rain_mm=rain_mm, soil_t=soil_t, soil_m=soil_m)


def _rain_parts(s: DailySeries, i: int, sp: Species) -> tuple[float, bool]:
    """(czynnik opadu, czy zadziałała kara za suchą glebę)."""
    total = 0.0
    for k in range(RAIN_WINDOW[0], RAIN_WINDOW[1] + 1):
        if i - k < 0:
            continue
        core = RAIN_CORE_WINDOW[0] <= k <= RAIN_CORE_WINDOW[1]
        total += (RAIN_CORE_WEIGHT if core else RAIN_EDGE_WEIGHT) * s.precip[i - k]
    rain = (total - sp.rain_min) / (sp.rain_full - sp.rain_min)
    rain = min(1.0, max(0.0, rain))
    moisture = _mean_back(s.soil_moisture, i, MOISTURE_LOOKBACK)
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


def weather_multiplier(s: DailySeries, i: int, sp: Species) -> WeatherComponents:
    rain = rain_factor(s, i, sp)
    temp = temp_factor(s, i, sp)
    season = season_factor(s.dates[i], sp)
    return WeatherComponents(w=rain * temp * season, rain=rain, temp=temp, season=season)


def limiting_factor(
    comps: WeatherComponents, s: DailySeries, i: int, sp: Species
) -> str | None:
    """Kod najsłabszej składowej < LIM_THRESHOLD; remis: season, temp, rain."""
    ordered = [("season", comps.season), ("temp", comps.temp), ("rain", comps.rain)]
    candidates = [(name, v) for name, v in ordered if v < LIM_THRESHOLD]
    if not candidates:
        return None
    name = min(candidates, key=lambda c: c[1])[0]  # min zachowuje kolejność przy remisie
    if name == "season":
        return "season"
    if name == "temp":
        return "cold" if weather_values(s, i).soil_t < sp.temp[1] else "hot"
    return "dry_soil" if _rain_parts(s, i, sp)[1] else "dry"
