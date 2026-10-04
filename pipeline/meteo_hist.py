"""Historyczne serie pogodowe (Open-Meteo Historical Forecast API) do walidacji modelu (spec H §4).

Te same zmienne i parser co prognoza (`forecast.weather`), więc składowe `w` liczą się identycznie.
"""
import json
import time
from datetime import date, timedelta
from pathlib import Path

from forecast.model import DailySeries
from forecast.weather import PARAMS, _request, daily_from_response
from pipeline.grid import cell_center

HIST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
HIST_START = date(2022, 1, 1)
SEASON_FROM = (4, 10)  # 1 maja − 21 dni okna opadu
SEASON_TO = (11, 30)
REQUEST_PAUSE_S = 1
RETRIES = 3


def year_range(year: int, today: date) -> tuple[date, date] | None:
    if year < HIST_START.year:
        return None
    start = date(year, *SEASON_FROM)
    end = min(date(year, *SEASON_TO), today - timedelta(days=1))
    return None if start >= today or end < start else (start, end)


def hist_params(cell: str, start: date, end: date) -> dict:
    lat, lon = cell_center(cell)
    keep = {k: v for k, v in PARAMS.items() if k not in ("past_days", "forecast_days")}
    return {**keep, "latitude": lat, "longitude": lon,
            "start_date": start.isoformat(), "end_date": end.isoformat()}


def fetch_year(cell: str, year: int, cache_dir: Path, *, today: date, refresh: bool = False,
               session=None, sleep=time.sleep) -> DailySeries | None:
    """Seria dzienna komórki dla sezonu roku; None, gdy rok poza zakresem API."""
    rng = year_range(year, today)
    if rng is None:
        return None
    cache_dir = Path(cache_dir)
    path = cache_dir / f"{cell}_{year}.json"
    if path.exists() and not refresh:
        obj = json.loads(path.read_text(encoding="utf-8"))
    else:
        obj = _request(hist_params(cell, *rng), RETRIES, sleep, session, url=HIST_URL)[0]
        cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(obj), encoding="utf-8")
        tmp.replace(path)
        sleep(REQUEST_PAUSE_S)
    return daily_from_response(obj)
