"""Klient Open-Meteo: opad dobowy oraz temperatura i wilgotność gleby jako pełne serie dzienne."""
import time
from collections import defaultdict
from datetime import date

import requests

from forecast.model import DailySeries

API_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_S = 30
# Limit minutowy Open-Meteo (429): zapytanie o 30 punktów z 37 dniami i trzema zmiennymi godzinowymi
# waży ~95 „wywołań”, więc przy ~23 partiach limit 600/min wypada pod koniec przebiegu. Czekamy ~minutę.
RATE_LIMIT_WAIT_S = 65
RATE_LIMIT_RETRIES = 6
PARAMS = {
    "daily": "precipitation_sum,et0_fao_evapotranspiration,temperature_2m_min",
    "hourly": "soil_temperature_6cm,soil_moisture_3_to_9cm,soil_moisture_9_to_27cm",
    "past_days": 30,
    "forecast_days": 7,
    "timezone": "Europe/Warsaw",
}


class WeatherError(Exception):
    pass


class RateLimitError(WeatherError):
    """429 utrzymuje się po RATE_LIMIT_RETRIES oczekiwaniach (np. limit dzienny/godzinowy) — przerywa cały przebieg."""


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


def _try_series(obj: dict, path: list[str]) -> list | None:
    """Zwraca listę wartości lub None, gdy klucz nie istnieje."""
    cur = obj
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur if isinstance(cur, list) else None


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

    # Nowe zmienne opcjonalne: brak klucza lub same null → None.
    et0_raw = _try_series(obj, ["daily", "et0_fao_evapotranspiration"])
    et0 = [0.0 if e is None else float(e) for e in et0_raw] if et0_raw is not None else None

    t2m_min_raw = _try_series(obj, ["daily", "temperature_2m_min"])
    t2m_min = None
    if t2m_min_raw is not None:
        try:
            t2m_min = _fill_nearest(t2m_min_raw, "temperature_2m_min")
        except WeatherError:
            t2m_min = None

    moist_deep_raw = _try_series(obj, ["hourly", "soil_moisture_9_to_27cm"])
    moist_deep = None
    if moist_deep_raw is not None:
        try:
            moist_deep = _fill_nearest(_daily_means(h_time, moist_deep_raw, day_strs), "soil_moisture_9_to_27cm")
        except WeatherError:
            moist_deep = None

    return DailySeries(
        dates=dates,
        precip=[0.0 if p is None else float(p) for p in precip],
        soil_temp=_fill_nearest(temp, "soil_temperature_6cm"),
        soil_moisture=_fill_nearest(moist, "soil_moisture_3_to_9cm"),
        et0=et0,
        t2m_min=t2m_min,
        soil_moisture_deep=moist_deep,
    )


def _request(params: dict, retries: int, sleep, session) -> list[dict]:
    http = session or requests
    last: Exception | None = None
    limited = 0
    attempt = 0
    while attempt < retries:
        try:
            r = http.get(API_URL, params=params, timeout=TIMEOUT_S)
            if r.status_code == 429:
                if limited >= RATE_LIMIT_RETRIES:
                    # Kolejne partie też dostałyby 429 — kończymy przebieg zamiast zużywać limit.
                    raise RateLimitError(
                        f"Open-Meteo: limit żądań (429) nadal po {RATE_LIMIT_RETRIES} oczekiwaniach "
                        f"po {RATE_LIMIT_WAIT_S} s; przerywam przebieg")
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


def fetch_series(points: list[tuple[str, float, float]], *, batch: int = 30,
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
