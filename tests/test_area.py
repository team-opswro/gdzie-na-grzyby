import geopandas as gpd
import yaml
from shapely.geometry import box

from pipeline import area
from pipeline.area import build_area_from_outlines
from pipeline.fetch_bdl import FIELDS_YAML


def test_area_is_union_of_outlines_without_clipping():
    outlines = gpd.GeoDataFrame({"prefix": ["a", "b"], "name": ["A", "B"]},
                                geometry=[box(17, 50, 18, 51), box(17.5, 50.5, 18.5, 51.5)],
                                crs=4326)
    a = build_area_from_outlines(outlines)
    assert a.is_valid
    for g in outlines.geometry:
        assert a.covers(g)
    assert abs(a.area - (2 - 0.25)) < 1e-9


def test_area_accepts_geometry_list():
    g = box(17, 50, 18, 51)
    assert build_area_from_outlines([g]).equals(g)


def test_yaml_has_empty_api_districts_and_no_districts():
    cfg = yaml.safe_load(FIELDS_YAML.read_text(encoding="utf-8"))
    assert cfg["api_districts"] == []
    assert "districts" not in cfg


def test_main_unions_ingest_outlines_and_api_outline(tmp_path, monkeypatch):
    outl = tmp_path / "n.geojson"
    gpd.GeoDataFrame({"prefix": ["02-99"], "name": ["T"]},
                     geometry=[box(17, 50, 17.1, 50.1)], crs=4326).to_file(outl, driver="GeoJSON")
    monkeypatch.setattr(area.yaml, "safe_load", lambda _t: {"api_districts": [
        {"name": "Api", "prefix": "06-20"}, {"name": "Dup", "prefix": "02-99"}]})
    calls = []

    def fake(session, base, prefix):
        calls.append(prefix)
        return box(18, 51, 18.1, 51.1)
    monkeypatch.setattr(area, "fetch_outline", fake)
    out = tmp_path / "obszar.geojson"
    assert area.main(["--outlines", str(outl), "--out", str(out)]) == 0
    assert calls == ["06-20"]  # prefiks z paczki nie jest pobierany z API
    g = gpd.read_file(out).geometry.iloc[0]
    assert g.covers(box(17.01, 50.01, 17.09, 50.09)) and g.covers(box(18.01, 51.01, 18.09, 51.09))


def test_main_requires_ingest_output(tmp_path, capsys):
    assert area.main(["--outlines", str(tmp_path / "nie.geojson"),
                      "--out", str(tmp_path / "o.geojson")]) == 1
    assert "ingest" in capsys.readouterr().err
