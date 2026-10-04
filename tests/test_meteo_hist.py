import json
from datetime import date
from pathlib import Path

import responses

from forecast.weather import PARAMS
from pipeline.meteo_hist import HIST_URL, fetch_year, hist_params, year_range

FIX = Path(__file__).parent / "fixtures" / "openmeteo_two_points.json"
TODAY = date(2026, 10, 3)


def one_point():
    return json.loads(FIX.read_text(encoding="utf-8"))[0]


def test_year_range_bounds():
    assert year_range(2021, TODAY) is None
    assert year_range(2023, TODAY) == (date(2023, 4, 10), date(2023, 11, 30))
    assert year_range(2026, TODAY) == (date(2026, 4, 10), date(2026, 10, 2))
    assert year_range(2026, date(2026, 4, 10)) is None


def test_hist_params_has_no_past_or_forecast_days():
    p = hist_params("493_189", date(2023, 4, 10), date(2023, 11, 30))
    assert "past_days" not in p and "forecast_days" not in p
    assert (p["latitude"], p["longitude"]) == (49.35, 18.95)
    assert p["hourly"] == PARAMS["hourly"] and p["daily"] == PARAMS["daily"]
    assert p["start_date"] == "2023-04-10" and p["end_date"] == "2023-11-30"


@responses.activate
def test_fetch_year_caches(tmp_path):
    responses.get(HIST_URL, json=one_point())
    slept = []
    s = fetch_year("493_189", 2023, tmp_path, today=TODAY, sleep=slept.append)
    assert s.dates[0] == date(2026, 10, 1)  # daty z fixture'a
    assert len(responses.calls) == 1 and slept == [1]
    assert (tmp_path / "493_189_2023.json").exists()
    again = fetch_year("493_189", 2023, tmp_path, today=TODAY, sleep=slept.append)
    assert again.dates == s.dates and len(responses.calls) == 1


@responses.activate
def test_fetch_year_before_2022_no_request(tmp_path):
    assert fetch_year("493_189", 2021, tmp_path, today=TODAY) is None
    assert len(responses.calls) == 0
