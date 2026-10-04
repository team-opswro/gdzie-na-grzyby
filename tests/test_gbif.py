import json
from datetime import date
from pathlib import Path

import pytest
import responses
from shapely.geometry import box

from pipeline import gbif
from pipeline.gbif import (
    GBIF_API, GbifError, area_wkt, base_query, clean, fetch_records, load_observations, match_taxon,
    parse_day,
)

FIX = Path(__file__).parent / "fixtures"
AREA = box(17.0, 49.5, 19.0, 51.0)
SEARCH = GBIF_API + "/occurrence/search"
MATCH = GBIF_API + "/species/match"


def fx(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def no_sleep(_s):
    pass


@responses.activate
def test_match_taxon_accepts_species_exact_and_rejects_genus():
    responses.get(MATCH, json=fx("gbif_match.json"))
    responses.get(MATCH, json={"usageKey": 1, "rank": "GENUS", "matchType": "EXACT"})
    responses.get(MATCH, json={"matchType": "NONE"})
    assert match_taxon("Boletus edulis") == 5249504
    assert match_taxon("Boletus") is None
    assert match_taxon("Xyz abc") is None
    assert "kingdom=Fungi" in responses.calls[0].request.url


def test_area_wkt_counter_clockwise():
    assert area_wkt(box(17.0, 49.5, 19.0, 51.0)) == \
        "POLYGON((17.0 49.5, 19.0 49.5, 19.0 51.0, 17.0 51.0, 17.0 49.5))"


def test_base_query_params():
    q = base_query(AREA, 2026)
    assert q["hasCoordinate"] == "true" and q["hasGeospatialIssue"] == "false"
    assert q["basisOfRecord"] == "HUMAN_OBSERVATION" and q["occurrenceStatus"] == "PRESENT"
    assert q["year"] == "2000,2026" and q["limit"] == 300
    assert q["geometry"].startswith("POLYGON((")


def _pages():
    responses.get(SEARCH, json=fx("gbif_page0.json"))
    responses.get(SEARCH, json=fx("gbif_page1.json"))


@responses.activate
def test_fetch_paginates_and_caches(tmp_path):
    _pages()
    recs = fetch_records({"taxonKey": 1}, tmp_path, sleep=no_sleep)
    assert [r["key"] for r in recs] == [1, 2, 3, 4]
    assert len(responses.calls) == 2
    assert "offset=300" in responses.calls[1].request.url
    again = fetch_records({"taxonKey": 1}, tmp_path, sleep=no_sleep)
    assert again == recs and len(responses.calls) == 2


@responses.activate
def test_fetch_refresh_refetches(tmp_path):
    _pages()
    _pages()
    fetch_records({"taxonKey": 1}, tmp_path, sleep=no_sleep)
    fetch_records({"taxonKey": 1}, tmp_path, refresh=True, sleep=no_sleep)
    assert len(responses.calls) == 4


@responses.activate
def test_fetch_stops_at_max_records(tmp_path, monkeypatch):
    monkeypatch.setattr(gbif, "MAX_RECORDS", 300)
    _pages()
    recs = fetch_records({"taxonKey": 1}, tmp_path, sleep=no_sleep)
    assert len(responses.calls) == 1 and len(recs) == 2


@responses.activate
def test_fetch_retries_then_fails(tmp_path):
    for _ in range(3):
        responses.get(SEARCH, status=503)
    slept = []
    with pytest.raises(GbifError):
        fetch_records({"taxonKey": 1}, tmp_path, sleep=slept.append)
    assert len(responses.calls) == 3


def test_parse_day_formats():
    assert parse_day({"year": 2023, "month": 9, "day": 14, "eventDate": "2023-09-14"}) == date(2023, 9, 14)
    assert parse_day({"year": 2023, "month": 9, "day": 14,
                      "eventDate": "2023-09-14T10:00:00+02:00"}) == date(2023, 9, 14)
    assert parse_day({"year": 2023, "month": 9, "eventDate": "2023-09-01/2023-09-30"}) is None
    assert parse_day({"year": 2023, "month": 9, "day": 1, "eventDate": "2023-09-01/2023-09-30"}) is None
    assert parse_day({"year": 2023, "month": 2, "day": 30}) is None


def test_clean_filters_uncertainty_area_and_duplicates():
    recs = fx("gbif_page0.json")["results"] + fx("gbif_page1.json")["results"]
    recs.append(dict(recs[0]))
    df = clean(recs, AREA, "borowik")
    # 1: ok; 2: niepewność 150; 3: brak niepewności; 4: poza obszarem; duplikat 1
    assert list(df["gbif_id"]) == [1]
    assert list(df.columns) == ["species", "gbif_id", "lat", "lon", "date"]
    assert df.iloc[0]["species"] == "borowik" and df.iloc[0]["date"] == date(2023, 9, 14)


@responses.activate
def test_load_observations_warns_on_unmatched_taxon(tmp_path, monkeypatch):
    monkeypatch.setattr(gbif, "FIRST_YEAR", 2026)  # tło: jedno zapytanie roczne
    responses.get(MATCH, json={"matchType": "NONE"})
    responses.get(MATCH, json=fx("gbif_match.json"))
    _pages()  # gatunek
    _pages()  # tło (kingdomKey=5, rok 2026)
    pres, bg, warns = load_observations({"xyz": "Xyz abc", "borowik": "Boletus edulis"}, AREA,
                                        tmp_path, sleep=no_sleep, year_to=2026)
    assert len(warns) == 1 and "xyz" in warns[0]
    assert set(pres["species"]) == {"borowik"} and set(bg["species"]) == {"*"}
    assert (tmp_path / "borowik" / "0.json").exists()
    assert (tmp_path / "fungi" / "2026" / "0.json").exists()
    assert "kingdomKey=5" in responses.calls[-1].request.url


@responses.activate
def test_background_fetched_per_year(tmp_path, monkeypatch):
    # głębokie stronicowanie GBIF jest bardzo wolne -> tło pobierane rok po roku (małe offsety)
    monkeypatch.setattr(gbif, "FIRST_YEAR", 2024)
    for _ in range(3):
        responses.get(SEARCH, json={"endOfRecords": True, "results": []})
    load_observations({}, AREA, tmp_path, sleep=no_sleep, year_to=2026)
    years = [c.request.url.split("year=")[1].split("&")[0] for c in responses.calls]
    assert years == ["2024", "2025", "2026"]


@responses.activate
def test_big_year_split_into_months(tmp_path, monkeypatch):
    monkeypatch.setattr(gbif, "FIRST_YEAR", 2026)
    responses.get(SEARCH, json={"count": 5000, "endOfRecords": False, "results": []})
    for _ in range(12):
        responses.get(SEARCH, json={"endOfRecords": True, "results": []})
    load_observations({}, AREA, tmp_path, sleep=no_sleep, year_to=2026)
    months = [c.request.url.split("month=")[1].split("&")[0] for c in responses.calls[1:]]
    assert months == [str(m) for m in range(1, 13)]
    assert (tmp_path / "fungi" / "2026-12" / "0.json").exists()
