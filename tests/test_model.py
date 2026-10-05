import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from forecast.model import WET_GAMMA_BASE, wet_adjust, wet_gamma
from forecast.model import (
    ET_ALPHA,
    FROST_FLOOR,
    FROST_RECOVERY_DAYS,
    LIM_THRESHOLD,
    MOIST_FLOOR,
    PULSE_DROP_FULL,
    PULSE_MAX,
    RAIN_WINDOW,
    DailySeries,
    WeatherComponents,
    frost_factor,
    limiting_factor,
    pulse_factor,
    rain_factor,
    season_factor,
    bucket_fraction,
    dry_days,
    moist_factor,
    temp_factor,
    water,
    weather_multiplier,
    weather_values,
)
from forecast.species import load_species

B = load_species()["borowik"]


def series(precip_by_k, temp=15.0, moist=0.3, deep=None, et0=None, t2m_min=None, day=date(2026, 8, 15)):
    dates = [day + timedelta(days=d) for d in range(-30, 7)]
    i = 30
    precip = [0.0] * len(dates)
    for k, mm in precip_by_k.items():
        precip[i - k] = mm
    n = len(dates)
    temps = [float(v) for v in temp] if isinstance(temp, (list, tuple)) else [float(temp)] * n
    return DailySeries(
        dates, precip, temps, [moist] * n,
        et0=[float(e) for e in et0] if et0 is not None else None,
        t2m_min=[float(t) for t in t2m_min] if t2m_min is not None else None,
        soil_moisture_deep=[float(d) for d in deep] if deep is not None else None,
    ), i


def test_rain_40mm_in_core_window_is_full():
    assert rain_factor(*series({10: 40}), B) == 1.0


def test_rain_40mm_at_k5_half_weight():
    assert rain_factor(*series({5: 40}), B) == pytest.approx(1 / 3)


def test_rain_outside_window_ignored():
    assert rain_factor(*series({3: 100, 25: 100}), B) == 0.0


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
    # deszcz w oknie impulsu, potem 12 suchych dni z ET0 3 mm -> przesuszone podłoże
    et0 = [3.0] * 37
    s, i = series({k: 40 for k in range(13, 22)}, et0=et0)
    assert limiting_factor(weather_multiplier(s, i, B), s, i, B) == "dry_soil"
    # brak deszczu w oknie, ale podłoże pełne (bez et0) -> za mało deszczu
    s, i = series({})
    assert limiting_factor(weather_multiplier(s, i, B), s, i, B) == "dry"


def test_limiting_factor_season():
    s, i = series(_full_rain(), day=date(2026, 1, 15))
    assert limiting_factor(weather_multiplier(s, i, B), s, i, B) == "season"


def test_limiting_factor_tie_order():
    s, i = series(_full_rain())
    comps = WeatherComponents(w=0.25, rain=0.9, temp=0.5, season=0.5, pulse=1.0, frost=1.0)
    assert limiting_factor(comps, s, i, B) == "season"
    comps = WeatherComponents(w=0.25, rain=0.5, temp=0.5, season=0.9, pulse=1.0, frost=1.0)
    # remis temp == rain -> temp; średnia gleby 15 >= temp[1] -> hot
    assert limiting_factor(comps, s, i, B) == "hot"
    assert LIM_THRESHOLD == 0.8


def test_alpha_zero_reproduces_old_rain(monkeypatch):
    monkeypatch.setattr("forecast.model.ET_ALPHA", 0.0)
    assert rain_factor(*series({10: 40}), B) == 1.0
    assert rain_factor(*series({5: 40}), B) == pytest.approx(1 / 3)
    assert rain_factor(*series({3: 100, 25: 100}), B) == 0.0


def test_et0_does_not_change_rain_impulse():
    # spec M: parowanie liczy wiadro (moist), rain to czysty impuls opadu
    s, i = series({10: 40}, et0=[5.0] * 37)
    with_et0 = rain_factor(s, i, B)
    s.et0 = None
    assert with_et0 == rain_factor(s, i, B) == 1.0
    assert ET_ALPHA == 0.0


def test_soil_moisture_from_open_meteo_no_longer_penalizes():
    assert rain_factor(*series({10: 40}, moist=0.05), B) == 1.0


# --- bilans wodny podłoża (spec M) ---

def test_bucket_full_after_rain_and_drains_with_et0():
    s, i = series({1: 30.0}, et0=[2.5] * 37)
    assert bucket_fraction(s, i) == pytest.approx(1.0)
    s, i = series({}, et0=[2.5] * 37)  # 30 dni bez deszczu
    assert bucket_fraction(s, i) == 0.0


def test_bucket_counts_days_before_i_only():
    s, i = series({0: 30.0}, et0=[0.0] * 37)
    s.et0[i - 1] = 5.0  # wczoraj ubyło 4 mm (KC 0,8), dzisiejszy deszcz jeszcze się nie liczy
    assert bucket_fraction(s, i) == pytest.approx(1 - 4 / 25)


def test_bucket_start_and_no_et0():
    s, _ = series({}, et0=[2.5] * 37)
    assert bucket_fraction(s, 0) == 1.0 and dry_days(s, 0) == 0
    s, i = series({})
    assert bucket_fraction(s, i) is None and moist_factor(s, i) == 1.0
    assert weather_values(s, i).water is None


@pytest.mark.parametrize("f,exp", [(0.3, 0.55), (0.05, MOIST_FLOOR), (0.1, MOIST_FLOOR), (0.8, 1.0), (0.5, 1.0)])
def test_moist_ramp_and_floor(monkeypatch, f, exp):
    monkeypatch.setattr("forecast.model.bucket_fraction", lambda s, i: f)
    assert moist_factor(*series({})) == pytest.approx(exp)


def test_dry_days():
    s, i = series({3: 5.0, 1: 0.5}, et0=[2.0] * 37)
    assert dry_days(s, i) == 2  # ostatni deszcz 3 dni temu: pełne suche dni 2 i 1 (0,5 mm < 1 mm)
    s, i = series({1: 5.0}, et0=[2.0] * 37)
    assert dry_days(s, i) == 0
    s, i = series({}, et0=[2.0] * 37)
    assert dry_days(s, i) == 30
    assert weather_values(s, i).dry_days == 30


def test_field_case_505_176():
    raw = json.loads((Path(__file__).parent / "fixtures" / "m_case_505_176.json").read_text())
    raw["dates"] = [date.fromisoformat(d) for d in raw["dates"]]
    s = DailySeries(**raw)
    i = s.dates.index(date(2026, 10, 4))
    c = weather_multiplier(s, i, B)
    assert c.w <= 0.6  # stary model: 0,80
    assert c.moist == pytest.approx(0.61, abs=0.02)
    assert limiting_factor(c, s, i, B) == "dry_soil"
    assert dry_days(s, i) == 9


def test_wet_site_lifts_w_in_deep_drought():
    assert wet_adjust(0.1, MOIST_FLOOR, 100) > 0.1
    assert wet_adjust(0.1, MOIST_FLOOR, 0) < 0.1


def test_pulse_values():
    def make(drop):
        t = [15.0] * 37
        # okno wcześniejsze (i-14..i-8) cieplejsze o `drop` od późniejszego (i-5..i-1)
        for k in range(8, 15):
            t[30 - k] = 15.0 + drop
        return t

    assert pulse_factor(*series({}, temp=make(0))) == 1.0
    assert pulse_factor(*series({}, temp=make(1.5))) == pytest.approx(1.0 + PULSE_MAX * (1.5 / PULSE_DROP_FULL))
    assert pulse_factor(*series({}, temp=make(3.0))) == pytest.approx(1.0 + PULSE_MAX)
    assert pulse_factor(*series({}, temp=make(6.0))) == pytest.approx(1.0 + PULSE_MAX)
    # wzrost temperatury zamiast spadku
    t = [15.0] * 37
    for k in range(1, 6):
        t[30 - k] = 20.0
    assert pulse_factor(*series({}, temp=t)) == 1.0
    # za krótka seria
    short = DailySeries([date(2026, 8, 1)] * 5, [0.0] * 5, [15.0] * 5, [0.3] * 5)
    assert pulse_factor(short, 4) == 1.0


def test_frost_recovery():
    def make(frost_idx):
        t = [5.0] * 37
        t[frost_idx] = -5.0
        return t

    s, i = series({}, t2m_min=make(30))
    assert frost_factor(s, i, B) == pytest.approx(FROST_FLOOR)
    s, i = series({}, t2m_min=make(27))
    assert frost_factor(s, i, B) == pytest.approx(FROST_FLOOR + (1 - FROST_FLOOR) * 3 / FROST_RECOVERY_DAYS)
    s, i = series({}, t2m_min=make(23))
    assert frost_factor(s, i, B) == 1.0


def test_w_capped_at_one(monkeypatch):
    monkeypatch.setattr("forecast.model.rain_factor", lambda s, i, sp: 1.0)
    monkeypatch.setattr("forecast.model.temp_factor", lambda s, i, sp: 1.0)
    monkeypatch.setattr("forecast.model.season_factor", lambda d, sp: 1.0)
    monkeypatch.setattr("forecast.model.pulse_factor", lambda s, i: 1.0 + PULSE_MAX)
    monkeypatch.setattr("forecast.model.frost_factor", lambda s, i, sp: 1.0)
    s, i = series({})
    assert weather_multiplier(s, i, B).w == 1.0


def test_limiting_frost_and_tie_order():
    s, i = series(_full_rain())
    comps = WeatherComponents(w=0.04, rain=1.0, temp=0.2, season=1.0, pulse=1.0, frost=0.2)
    assert limiting_factor(comps, s, i, B) == "frost"
    comps = WeatherComponents(w=0.01, rain=1.0, temp=1.0, season=0.1, pulse=1.0, frost=0.1)
    assert limiting_factor(comps, s, i, B) == "season"


def test_series_without_new_fields_unchanged():
    s, i = series({10: 40})
    comps = weather_multiplier(s, i, B)
    assert comps.pulse == 1.0
    assert comps.frost == 1.0
    assert comps.moist == 1.0
    assert comps.rain == rain_factor(s, i, B)
    # bez et0 rain jest liczone tak, jakby ET_ALPHA=0
    s.et0 = [0.0] * len(s.dates)
    assert comps.rain == rain_factor(s, i, B)


# --- wilgotność miejsca (spec L) ---
WET_CASES = json.loads((Path(__file__).parent / "fixtures" / "wet_cases.json").read_text())["cases"]


@pytest.mark.parametrize("c", WET_CASES)
def test_wet_adjust_shared_cases(c):
    base = c.get("base", WET_GAMMA_BASE)
    assert wet_adjust(c["w"], c["rain"], c["wet"], base) == pytest.approx(c["expected"], abs=1e-6)


def test_wet_gamma_range():
    assert wet_gamma(50) == 1.0 and wet_gamma(0) == 3.0 and wet_gamma(100) == pytest.approx(1 / 3)
    assert wet_gamma(None) == 1.0


def test_wet_adjust_monotonic_in_wet():
    vals = [wet_adjust(0.6, 0.6, wet) for wet in range(0, 101, 10)]
    assert vals == sorted(vals)
