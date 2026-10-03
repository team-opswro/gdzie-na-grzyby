from datetime import date, timedelta

import pytest

from forecast.model import (
    DailySeries,
    rain_factor,
    season_factor,
    temp_factor,
    weather_multiplier,
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
