"""Testy pobierania parkingów z OpenStreetMap."""
import json

import requests
from pathlib import Path

import geopandas as gpd
import pytest
import responses
from shapely.geometry import Point, box

from pipeline import fetch_parkings as fp

FIXTURE = Path(__file__).parent / "fixtures" / "overpass_parking.json"


def test_tiles_cover_bounds():
    # (west, south, east, north) -> kafle (south, west, north, east)
    tiles = fp.tiles_for_bounds((17.2, 49.4, 18.1, 50.2))
    expected = [
        (49.0, 17.0, 49.5, 17.5),
        (49.0, 17.5, 49.5, 18.0),
        (49.0, 18.0, 49.5, 18.5),
        (49.5, 17.0, 50.0, 17.5),
        (49.5, 17.5, 50.0, 18.0),
        (49.5, 18.0, 50.0, 18.5),
        (50.0, 17.0, 50.5, 17.5),
        (50.0, 17.5, 50.5, 18.0),
        (50.0, 18.0, 50.5, 18.5),
    ]
    assert tiles == expected


def test_query_text():
    q = fp.query((49.0, 17.0, 49.5, 17.5))
    assert '[out:json][timeout:90]' in q
    assert 'nwr["amenity"="parking"](49.0,17.0,49.5,17.5)' in q
    assert 'out center tags;' in q


def test_elements_filters_and_centers():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    gdf = fp.elements_to_gdf(data["elements"])
    assert set(gdf["osm"]) == {"n1", "w2", "r9"}
    assert gdf.crs.to_epsg() == 4326
    name_map = dict(zip(gdf["osm"], gdf["name"]))
    assert name_map["n1"] == "Parking leśny"
    assert name_map["w2"] == "Parking przy drodze"
    fee_map = dict(zip(gdf["osm"], gdf["fee"]))
    assert fee_map["n1"] == "no"
    assert fee_map["w2"] == "yes"
    assert fee_map["r9"] is None


def test_near_forest_filter():
    # EPSG:2180, jednostki w metrach
    stands = gpd.GeoDataFrame(
        {"id": ["las_blisko", "las_daleko"]},
        geometry=[box(0, 0, 10, 10), box(1000, 0, 1010, 10)],
        crs=2180,
    )
    parkings = gpd.GeoDataFrame(
        {"osm": ["p100", "p1000"]},
        geometry=[Point(105, 5), Point(2000, 5)],
        crs=2180,
    )
    out = fp.near_forest(parkings, stands)
    assert list(out["osm"]) == ["p100"]


def test_fetch_tile_cache_and_retry(tmp_path):
    cache_dir = tmp_path / "cache"
    bbox = (49.0, 17.0, 49.5, 17.5)
    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)

    payload = {
        "elements": [
            {"type": "node", "id": 10, "lat": 49.1, "lon": 17.1, "tags": {"amenity": "parking"}}
        ]
    }
    with responses.RequestsMock() as rsps:
        rsps.add(responses.POST, fp.OVERPASS_URLS[0], status=429)
        rsps.add(responses.POST, fp.OVERPASS_URLS[1], json=payload)  # druga próba: serwer zapasowy
        els = fp.fetch_tile(bbox, cache_dir, sleep=fake_sleep)
        assert len(rsps.calls) == 2
        assert len(els) == 1
        assert els[0]["id"] == 10
        assert sleeps == [30, 5]  # backoff po 429 + pauza po pobraniu z sieci

        # drugi przebieg: cache hit, brak żądań
        els2 = fp.fetch_tile(bbox, cache_dir, sleep=fake_sleep)
        assert len(rsps.calls) == 2
        assert els2 == els
        assert sleeps == [30, 5]  # z cache: bez dodatkowych uśpień


def test_main_writes_geojson(tmp_path, monkeypatch, capsys):
    area_file = tmp_path / "obszar.geojson"
    gpd.GeoDataFrame(
        {"name": ["obszar"]}, geometry=[box(16.9, 49.9, 17.1, 50.1)], crs=4326
    ).to_file(area_file, driver="GeoJSON")

    stands_file = tmp_path / "stands.parquet"
    gpd.GeoDataFrame(
        {"id": ["s1"]}, geometry=[box(17.0, 50.0, 17.001, 50.001)], crs=4326
    ).to_parquet(stands_file)

    out = tmp_path / "parkingi.geojson"
    cache = tmp_path / "cache"

    # n1 wewnątrz lasu, n2 w promieniu ~170 m, n3 ponad 2 km od lasu
    elements = [
        {"type": "node", "id": 1, "lat": 50.0005, "lon": 17.0005, "tags": {"name": "W lesie"}},
        {"type": "node", "id": 2, "lat": 50.002, "lon": 17.002, "tags": {"fee": "yes"}},
        {"type": "node", "id": 3, "lat": 50.02, "lon": 17.02, "tags": {}},
    ]

    def fake_fetch_tile(bbox, cache_dir, refresh=False, session=None, sleep=None):
        return elements

    monkeypatch.setattr(fp, "fetch_tile", fake_fetch_tile)
    tile = (50.0, 17.0, 50.5, 17.5)
    monkeypatch.setattr(fp, "tiles_for_bounds", lambda b: [tile])

    rc = fp.main([
        "--area", str(area_file),
        "--parquet", str(stands_file),
        "--out", str(out),
        "--cache", str(cache),
    ])
    assert rc == 0
    captured = capsys.readouterr().out
    assert "parkingi" in captured

    gdf = gpd.read_file(out)
    assert set(gdf["osm"]) == {"n1", "n2"}
    assert gdf.loc[gdf["osm"] == "n1", "name"].iloc[0] == "W lesie"
    assert gdf.loc[gdf["osm"] == "n2", "fee"].iloc[0] == "yes"
    assert gdf.crs.to_epsg() == 4326


def test_main_missing_parquet(tmp_path, capsys):
    area_file = tmp_path / "obszar.geojson"
    gpd.GeoDataFrame(
        {"name": ["obszar"]}, geometry=[box(16.9, 49.9, 17.1, 50.1)], crs=4326
    ).to_file(area_file, driver="GeoJSON")
    rc = fp.main([
        "--area", str(area_file),
        "--parquet", str(tmp_path / "brak.parquet"),
    ])
    assert rc != 0
    assert "brak" in capsys.readouterr().err.lower() or "nie" in capsys.readouterr().err.lower()


def test_main_skips_tiles_outside_area(tmp_path, monkeypatch):
    area_file = tmp_path / "obszar.geojson"
    gpd.GeoDataFrame({"name": ["o"]}, geometry=[box(16.9, 49.9, 17.1, 50.1)], crs=4326).to_file(
        area_file, driver="GeoJSON")
    stands_file = tmp_path / "stands.parquet"
    gpd.GeoDataFrame({"id": ["s1"]}, geometry=[box(17.0, 50.0, 17.001, 50.001)], crs=4326).to_parquet(
        stands_file)
    called = []
    monkeypatch.setattr(fp, "fetch_tile", lambda bbox, *a, **k: called.append(bbox) or [])
    monkeypatch.setattr(fp, "tiles_for_bounds", lambda b: [(50.0, 17.0, 50.5, 17.5), (52.0, 20.0, 52.5, 20.5)])
    fp.main(["--area", str(area_file), "--parquet", str(stands_file), "--out", str(tmp_path / "p.geojson"),
             "--cache", str(tmp_path / "c")])
    assert called == [(50.0, 17.0, 50.5, 17.5)]


def test_fetch_tile_falls_back_to_second_endpoint(tmp_path):
    payload = {"elements": [{"type": "node", "id": 9, "lat": 50.0, "lon": 17.0, "tags": {}}]}
    sleeps = []
    with responses.RequestsMock() as rsps:
        rsps.add(responses.POST, fp.OVERPASS_URLS[0], status=504)
        rsps.add(responses.POST, fp.OVERPASS_URLS[1], json=payload)
        els = fp.fetch_tile((50.0, 17.0, 50.5, 17.5), tmp_path, sleep=sleeps.append)
    assert [e["id"] for e in els] == [9] and sleeps == [30, 5]


def test_failed_tile_split_into_quadrants(tmp_path, monkeypatch):
    calls = []

    def flaky(bbox, cache_dir, refresh=False, session=None, sleep=None):
        calls.append(bbox)
        if bbox[2] - bbox[0] > 0.3:  # kafel 0,5° — serwer nie wyrabia
            raise fp.OverpassError("504")
        return [{"type": "node", "id": len(calls), "lat": bbox[0], "lon": bbox[1], "tags": {}}]

    monkeypatch.setattr(fp, "fetch_tile", flaky)
    els = fp.fetch_area((50.0, 17.0, 50.5, 17.5), tmp_path)
    assert len(els) == 4
    assert calls[0] == (50.0, 17.0, 50.5, 17.5)
    assert sorted(calls[1:]) == [(50.0, 17.0, 50.25, 17.25), (50.0, 17.25, 50.25, 17.5),
                                 (50.25, 17.0, 50.5, 17.25), (50.25, 17.25, 50.5, 17.5)]


def test_split_gives_up_after_max_depth(tmp_path, monkeypatch):
    def always_fail(bbox, *a, **k):
        raise fp.OverpassError("504")
    monkeypatch.setattr(fp, "fetch_tile", always_fail)
    with pytest.raises(fp.OverpassError):
        fp.fetch_area((50.0, 17.0, 50.5, 17.5), tmp_path)


def test_main_skips_failed_tile_and_continues(tmp_path, monkeypatch, capsys):
    area_file = tmp_path / "obszar.geojson"
    gpd.GeoDataFrame({"name": ["o"]}, geometry=[box(16.9, 49.9, 17.6, 50.1)], crs=4326).to_file(
        area_file, driver="GeoJSON")
    stands_file = tmp_path / "stands.parquet"
    gpd.GeoDataFrame({"id": ["s1"]}, geometry=[box(17.0, 50.0, 17.001, 50.001)], crs=4326).to_parquet(
        stands_file)
    ok = [{"type": "node", "id": 1, "lat": 50.0005, "lon": 17.0005, "tags": {}}]

    def area(bbox, *a, **k):
        if bbox[1] >= 17.5:
            raise fp.OverpassError("504")
        return ok
    monkeypatch.setattr(fp, "fetch_area", area)
    monkeypatch.setattr(fp, "tiles_for_bounds", lambda b: [(50.0, 17.0, 50.5, 17.5), (50.0, 17.5, 50.5, 18.0)])
    out = tmp_path / "p.geojson"
    assert fp.main(["--area", str(area_file), "--parquet", str(stands_file), "--out", str(out),
                    "--cache", str(tmp_path / "c")]) == 0
    assert out.exists() and "pominięto 1" in capsys.readouterr().err


def test_remark_timeout_not_cached_and_retried(tmp_path):
    # Overpass przy przekroczeniu czasu zwraca 200 z "remark" i niepełną listą — to porażka, nie wynik
    bad = {"remark": "runtime error: Query timed out in \"query\" at line 2 after 91 seconds.", "elements": []}
    good = {"elements": [{"type": "node", "id": 5, "lat": 50.0, "lon": 17.0, "tags": {}}]}
    sleeps = []
    with responses.RequestsMock() as rsps:
        rsps.add(responses.POST, fp.OVERPASS_URLS[0], json=bad)
        rsps.add(responses.POST, fp.OVERPASS_URLS[1], json=good)
        els = fp.fetch_tile((50.0, 17.0, 50.5, 17.5), tmp_path, sleep=sleeps.append)
    assert [e["id"] for e in els] == [5]
    cached = json.loads(next(tmp_path.glob("parking_*.json")).read_text())
    assert "remark" not in cached


def test_other_errors_retried_then_overpass_error(tmp_path):
    with responses.RequestsMock() as rsps:
        rsps.add(responses.POST, fp.OVERPASS_URLS[0], status=502)
        rsps.add(responses.POST, fp.OVERPASS_URLS[1], body="<html>busy</html>")
        rsps.add(responses.POST, fp.OVERPASS_URLS[0], body=requests.ConnectionError("reset"))
        with pytest.raises(fp.OverpassError):
            fp.fetch_tile((50.0, 17.0, 50.5, 17.5), tmp_path, sleep=lambda s: None)
    assert not list(tmp_path.glob("parking_*.json"))
