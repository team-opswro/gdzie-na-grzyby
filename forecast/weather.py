"""Klient Open-Meteo: opad dobowy oraz temperatura i wilgotność gleby jako pełne serie dzienne."""
import time
from collections import defaultdict
from datetime import date

import requests

from forecast.model import DailySeries

API_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_S = 30
# Limit minutowy Open-Meteo (429): zapytanie o 50 punktów z 37 dniami godzinowych danych waży ~130
# „wywołań”, więc przy ~14 partiach limit 600/min wypada w połowie przebiegu. Czekamy ~minutę.
RATE_LIMIT_WAIT_S = 65
RATE_LIMIT_RETRIES = 6
PARAMS = {
    "daily": "precipitation_sum",
    "hourly": "soil_temperature_6cm,soil_moisture_3_to_9cm",
    "past_days": 30,
    "forecast_days": 7,
    "timezone": "Europe/Warsaw",
}


class WeatherError(Exception):
    pass


def _daily_means(times: list[str], values: list, dates: list[str]) -> list[float | None]:
    groups: dict[str, list[float]] = defaultdict(list)
    for t, v in zip(times, values):
        if v is not None:
            groups[t[:10]].append(v)
    return [sum(groups[d]) / len(groups[d]) if groups.get(d) else None for d in dates]


def _fill_nearest(values: list[float | None], name: str) -> list[float]:
    known = [i for i, v in enumerate(values) if v is not None]
    if not known:
        raise WeatherError(f"brak danych dla {name}")
    # min po (odległość, indeks): remis -> wcześniejszy dzień
    return [
        v if v is not None else values[min(known, key=lambda k: (abs(k - i), k))]
        for i, v in enumerate(values)
    ]


def daily_from_response(obj: dict) -> DailySeries:
    try:
        day_strs = obj["daily"]["time"]
        precip = obj["daily"]["precipitation_sum"]
        h_time = obj["hourly"]["time"]
        temp = _daily_means(h_time, obj["hourly"]["soil_temperature_6cm"], day_strs)
        moist = _daily_means(h_time, obj["hourly"]["soil_moisture_3_to_9cm"], day_strs)
        dates = [date.fromisoformat(d) for d in day_strs]
    except (KeyError, TypeError, ValueError) as e:
        raise WeatherError(f"nieprawidłowa odpowiedź Open-Meteo: {e!r}") from e
    return DailySeries(
        dates=dates,
        precip=[0.0 if p is None else float(p) for p in precip],
        soil_temp=_fill_nearest(temp, "soil_temperature_6cm"),
        soil_moisture=_fill_nearest(moist, "soil_moisture_3_to_9cm"),
    )


def _request(params: dict, retries: int, sleep, session) -> list[dict]:
    http = session or requests
    last: Exception | None = None
    limited = 0
    attempt = 0
    while attempt < retries:
        try:
            r = http.get(API_URL, params=params, timeout=TIMEOUT_S)
            if r.status_code == 429 and limited < RATE_LIMIT_RETRIES:
                limited += 1
                last = requests.HTTPError("429 Too Many Requests")
                sleep(RATE_LIMIT_WAIT_S)
                continue
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else [data]
        except (requests.RequestException, ValueError) as e:
            last = e
        attempt += 1
        if attempt < retries:
            sleep(2 ** (attempt - 1))
    raise WeatherError(f"Open-Meteo niedostępne po {retries} próbach: {last!r}")


def fetch_series(points: list[tuple[str, float, float]], *, batch: int = 50,
                 retries: int = 3, sleep=time.sleep, session=None) -> dict[str, DailySeries]:
    out: dict[str, DailySeries] = {}
    for i in range(0, len(points), batch):
        chunk = points[i:i + batch]
        params = {
            **PARAMS,
            "latitude": ",".join(str(p[1]) for p in chunk),
            "longitude": ",".join(str(p[2]) for p in chunk),
        }
        objs = _request(params, retries, sleep, session)
        if len(objs) != len(chunk):
            raise WeatherError(f"oczekiwano {len(chunk)} punktów, otrzymano {len(objs)}")
        for p, obj in zip(chunk, objs):
            out[p[0]] = daily_from_response(obj)
    return out
