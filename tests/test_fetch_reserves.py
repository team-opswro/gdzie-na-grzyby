import json
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import box

from pipeline import fetch_reserves
from pipeline.fetch_reserves import clip_reserves, wfs_params

FIXTURE = Path(__file__).parent / "fixtures" / "gdos_rezerwaty.json"
AREA = box(17.0, 50.0, 17.5, 50.5)


def test_wfs_params_axis_order():
    p = wfs_params((16.8, 49.9, 19.0, 51.3))
    assert p["typeNames"] == "GDOS:Rezerwaty" and p["outputFormat"] == "application/json"
    assert p["srsName"] == "EPSG:4326"
    assert p["service"] == "WFS" and p["version"] == "2.0.0" and p["request"] == "GetFeature"
    assert p["bbox"] == "49.9,16.8,51.3,19.0,urn:ogc:def:crs:EPSG::4326"


def test_clip_reserves_names_and_clipping():
    fc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    g = clip_reserves(fc, AREA)
    assert list(g.columns) == ["name", "geometry"] and g.crs.to_epsg() == 4326
    names = set(g["name"])
    assert names == {"Rezerwat Przykladowy Brzeg", "Rezerwat Przykladowy Wewnatrz"}
    assert all(AREA.buffer(1e-9).contains(geom) for geom in g.geometry)


def test_clip_reserves_empty_raises():
    with pytest.raises(ValueError):
        clip_reserves({"type": "FeatureCollection", "features": []}, AREA)


def test_main_keeps_existing_file_on_error(tmp_path, monkeypatch):
    area_file = tmp_path / "obszar.geojson"
    gpd.GeoDataFrame({"name": ["o"]}, geometry=[AREA], crs=4326).to_file(area_file, driver="GeoJSON")
    out = tmp_path / "rez.geojson"
    out.write_text("STARE")
    monkeypatch.setattr(fetch_reserves, "_get_json", lambda *a, **k: {"features": []})
    assert fetch_reserves.main(["--area", str(area_file), "--out", str(out)]) != 0
    assert out.read_text() == "STARE"


def test_main_writes_output(tmp_path, monkeypatch):
    area_file = tmp_path / "obszar.geojson"
    gpd.GeoDataFrame({"name": ["o"]}, geometry=[AREA], crs=4326).to_file(area_file, driver="GeoJSON")
    out = tmp_path / "rez.geojson"
    fc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    monkeypatch.setattr(fetch_reserves, "_get_json", lambda *a, **k: fc)
    assert fetch_reserves.main(["--area", str(area_file), "--out", str(out)]) == 0
    assert len(gpd.read_file(out)) == 2
