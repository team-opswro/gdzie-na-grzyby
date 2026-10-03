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


def rain_factor(s: DailySeries, i: int, sp: Species) -> float:
    total = 0.0
    for k in range(RAIN_WINDOW[0], RAIN_WINDOW[1] + 1):
        if i - k < 0:
            continue
        core = RAIN_CORE_WINDOW[0] <= k <= RAIN_CORE_WINDOW[1]
        total += (RAIN_CORE_WEIGHT if core else RAIN_EDGE_WEIGHT) * s.precip[i - k]
    rain = (total - sp.rain_min) / (sp.rain_full - sp.rain_min)
    rain = min(1.0, max(0.0, rain))
    moisture = _mean_back(s.soil_moisture, i, MOISTURE_LOOKBACK)
    if moisture is not None and moisture < sp.soil_moisture_min:
        rain *= MOISTURE_PENALTY
    return rain


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
