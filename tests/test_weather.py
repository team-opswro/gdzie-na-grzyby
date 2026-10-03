import json
from datetime import date
from pathlib import Path

import pytest
import requests
import responses

from forecast.weather import API_URL, WeatherError, daily_from_response, fetch_series

FIX = Path(__file__).parent / "fixtures" / "openmeteo_two_points.json"
POINTS = [("a", 50.65, 17.9), ("b", 50.75, 17.9)]


def fixture():
    return json.loads(FIX.read_text(encoding="utf-8"))


def test_daily_aggregates_hourly_ignoring_nulls():
    s = daily_from_response(fixture()[0])
    assert s.dates == [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)]
    assert s.soil_temp[0] == pytest.approx(12.0)
    assert s.soil_moisture[0] == pytest.approx(0.32)
    assert s.soil_temp[2] == pytest.approx(9.5)
    assert s.precip[0] == 2.5


def test_missing_day_filled_from_nearest():
    s = daily_from_response(fixture()[0])
    assert s.soil_temp[1] == s.soil_temp[0]  # remis -> wcześniejszy
    assert s.soil_moisture[1] == s.soil_moisture[0]
    assert s.precip[1] == 0.0


def test_variable_without_any_data_raises():
    obj = fixture()[0]
    obj["hourly"]["soil_temperature_6cm"] = [None] * len(obj["hourly"]["time"])
    with pytest.raises(WeatherError):
        daily_from_response(obj)


@responses.activate
def test_fetch_maps_points_in_order():
    responses.get(API_URL, json=fixture())
    out = fetch_series(POINTS, sleep=lambda s: None)
    assert list(out) == ["a", "b"]
    assert out["a"].soil_temp[0] == pytest.approx(12.0)
    assert out["b"].precip == [0.0, 1.0, 3.0]
    assert len(responses.calls) == 1


@responses.activate
def test_fetch_single_point_object_response():
    responses.get(API_URL, json=fixture()[0])
    out = fetch_series(POINTS[:1], sleep=lambda s: None)
    assert out["a"].soil_temp[0] == pytest.approx(12.0)


@responses.activate
def test_fetch_batches_points():
    responses.get(API_URL, json=fixture()[0])
    out = fetch_series(POINTS, batch=1, sleep=lambda s: None)
    assert list(out) == ["a", "b"]
    assert len(responses.calls) == 2


@responses.activate
def test_fetch_retries_then_succeeds():
    responses.get(API_URL, status=500)
    responses.get(API_URL, status=500)
    responses.get(API_URL, json=fixture())
    sleeps = []
    out = fetch_series(POINTS, sleep=sleeps.append)
    assert set(out) == {"a", "b"}
    assert sleeps == [1, 2]


@responses.activate
def test_fetch_raises_after_retries():
    for _ in range(4):
        responses.get(API_URL, status=500)
    sleeps = []
    with pytest.raises(WeatherError):
        fetch_series(POINTS, sleep=sleeps.append)
    assert sleeps == [1, 2]
    assert len(responses.calls) == 3


@responses.activate
def test_fetch_retries_on_connection_error():
    responses.get(API_URL, body=requests.ConnectionError("boom"))
    responses.get(API_URL, json=fixture())
    out = fetch_series(POINTS, sleep=lambda s: None)
    assert set(out) == {"a", "b"}


@responses.activate
def test_fetch_sends_required_params():
    responses.get(API_URL, json=fixture())
    fetch_series(POINTS, sleep=lambda s: None)
    q = responses.calls[0].request.params
    assert q["latitude"] == "50.65,50.75"
    assert q["longitude"] == "17.9,17.9"
    assert q["past_days"] == "30"
    assert q["forecast_days"] == "7"
    assert q["timezone"] == "Europe/Warsaw"
    assert q["daily"] == "precipitation_sum"
    assert q["hourly"] == "soil_temperature_6cm,soil_moisture_3_to_9cm"
