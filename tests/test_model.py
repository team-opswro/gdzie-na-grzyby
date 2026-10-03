from datetime import date, timedelta

import pytest

from forecast.model import (
    LIM_THRESHOLD,
    RAIN_WINDOW,
    DailySeries,
    WeatherComponents,
    limiting_factor,
    rain_factor,
    season_factor,
    temp_factor,
    weather_multiplier,
    weather_values,
)
from forecast.species import load_species

B = load_species()["borowik"]


def series(precip_by_k, temp=15.0, moist=0.3, day=date(2026, 8, 15)):
    dates = [day + timedelta(days=d) for d in range(-30, 7)]
    i = 30
    precip = [0.0] * len(dates)
    for k, mm in precip_by_k.items():
        precip[i - k] = mm
    n = len(dates)
    return DailySeries(dates, precip, [float(temp)] * n, [moist] * n), i


def test_rain_40mm_in_core_window_is_full():
    assert rain_factor(*series({10: 40}), B) == 1.0


def test_rain_40mm_at_k5_half_weight():
    assert rain_factor(*series({5: 40}), B) == pytest.approx(1 / 3)


def test_rain_outside_window_ignored():
    assert rain_factor(*series({3: 100, 25: 100}), B) == 0.0


def test_dry_soil_halves_rain():
    assert rain_factor(*series({10: 40}, moist=0.1), B) == 0.5


@pytest.mark.parametrize("t,exp", [(15, 1.0), (9, 0.5), (23, 0.5), (3, 0.0), (30, 0.0)])
def test_temp_trapezoid(t, exp):
    assert temp_factor(*series({}, temp=t), B) == pytest.approx(exp)


@pytest.mark.parametrize(
    "d,exp",
    [
        (date(2026, 8, 15), 1.0),
        (date(2026, 6, 24), 0.55),
        (date(2026, 6, 10), 0.1),
        (date(2026, 11, 7), 0.55),
        (date(2026, 7, 1), 1.0),
        (date(2026, 10, 31), 1.0),
    ],
)
def test_season(d, exp):
    assert season_factor(d, B) == pytest.approx(exp)


def test_drought_scenario():
    assert weather_multiplier(*series({}), B).w < 0.1


def test_after_rain_scenario():
    assert weather_multiplier(*series({10: 40}), B).w > 0.8


def test_frost_scenario():
    assert weather_multiplier(*series({10: 40}, temp=-2), B).w == 0.0


def test_first_day_without_history_does_not_crash():
    s, _ = series({})
    assert weather_multiplier(s, 0, B).rain == 0.0


def _full_rain():
    return {k: 40 for k in range(RAIN_WINDOW[0], RAIN_WINDOW[1] + 1)}


def test_weather_values_window():
    s, i = series({k: 1.0 for k in range(0, 31)})
    n_days = RAIN_WINDOW[1] - RAIN_WINDOW[0] + 1
    assert weather_values(s, i).rain_mm == pytest.approx(n_days * 1.0) == 17.0
    s2, _ = series({k: 1.0 for k in range(0, 31)})
    # i=10: tylko indeksy 5..10 istnieją
    assert weather_values(s2, 10).rain_mm == pytest.approx(6.0)


def test_weather_values_means():
    s, i = series({}, temp=10.0, moist=0.2)
    s.soil_temp[i - 1] = 20.0
    s.soil_moisture[i - 3] = 0.5
    v = weather_values(s, i)
    assert v.soil_t == pytest.approx(sum(s.soil_temp[i - k] for k in range(1, 6)) / 5)
    assert v.soil_m == pytest.approx(sum(s.soil_moisture[i - k] for k in range(1, 4)) / 3)


def test_weather_values_temp_fallback_at_zero():
    s, _ = series({}, temp=9.0)
    assert weather_values(s, 0).soil_t == 9.0
    assert weather_values(s, 0).soil_m == 0.3


def test_limiting_factor_none_when_all_high():
    s, i = series(_full_rain())
    assert limiting_factor(weather_multiplier(s, i, B), s, i, B) is None


def test_limiting_factor_cold_vs_hot():
    s, i = series(_full_rain(), temp=3.0)
    assert limiting_factor(weather_multiplier(s, i, B), s, i, B) == "cold"
    s, i = series(_full_rain(), temp=30.0)
    assert limiting_factor(weather_multiplier(s, i, B), s, i, B) == "hot"


def test_limiting_factor_dry_vs_dry_soil():
    s, i = series({}, moist=0.05)
    assert limiting_factor(weather_multiplier(s, i, B), s, i, B) == "dry_soil"
    s, i = series({}, moist=0.3)
    assert limiting_factor(weather_multiplier(s, i, B), s, i, B) == "dry"


def test_limiting_factor_season():
    s, i = series(_full_rain(), day=date(2026, 1, 15))
    assert limiting_factor(weather_multiplier(s, i, B), s, i, B) == "season"


def test_limiting_factor_tie_order():
    s, i = series(_full_rain())
    comps = WeatherComponents(w=0.25, rain=0.9, temp=0.5, season=0.5)
    assert limiting_factor(comps, s, i, B) == "season"
    comps = WeatherComponents(w=0.25, rain=0.5, temp=0.5, season=0.9)
    # remis temp == rain -> temp; średnia gleby 15 >= temp[1] -> hot
    assert limiting_factor(comps, s, i, B) == "hot"
    assert LIM_THRESHOLD == 0.8
