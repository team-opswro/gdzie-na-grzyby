import geopandas as gpd
import yaml
from shapely.geometry import box

from pipeline.area import build_area
from pipeline.fetch_bdl import FIELDS_YAML


def test_build_area_union_covers_both_inputs():
    base = gpd.GeoDataFrame(geometry=[box(17, 50, 18, 51)], crs=4326)
    extra = [box(17.5, 50.5, 18.5, 51.5), box(16, 49, 16.5, 49.5)]
    area = build_area(base, extra)
    assert area.is_valid
    assert area.geom_type in ("Polygon", "MultiPolygon")
    assert area.covers(box(17, 50, 18, 51))
    for g in extra:
        assert area.covers(g)
    assert area.area > box(17, 50, 18, 51).area


def test_build_area_accepts_plain_geometry_and_no_extras():
    base = box(17, 50, 18, 51)
    assert build_area(base, []).equals(base)


def test_yaml_lists_whole_wroclaw_districts():
    cfg = yaml.safe_load(FIELDS_YAML.read_text(encoding="utf-8"))
    by_name = {d["name"]: d for d in cfg["districts"]}
    for name, prefix in (("Henryków", "13-02"), ("Oława", "13-20")):
        d = by_name[name]
        assert d["prefix"] == prefix
        assert d["layer"] == "RDLP_Wroclaw_wydzielenia"
        assert d["whole"] is True
