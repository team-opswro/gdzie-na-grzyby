import geopandas as gpd
import pytest
from shapely.geometry import Point, box

from pipeline import fetch_water as fw

POLY = """opolskie
1
  17.0 50.0
  18.0 50.0
  18.0 51.0
  17.0 51.0
END
!2
  17.4 50.4
  17.6 50.4
  17.6 50.6
END
END
"""


def test_parse_poly_skips_holes():
    p = fw.parse_poly(POLY)
    assert p.contains(Point(17.5, 50.5))  # dziura pominięta (zewnętrzny obrys)
    assert not p.contains(Point(18.5, 50.5))


def _osm_xml(tmp_path):
    """Staw ~1,2 ha, oczko ~0,1 ha, rów, rzeka i droga (pomijana)."""
    nodes, ways = [], []
    nid = [0]

    def node(lon, lat):
        nid[0] += 1
        nodes.append(f'<node id="{nid[0]}" version="1" lat="{lat}" lon="{lon}"/>')
        return nid[0]

    def way(wid, pts, tags, closed=False):
        ids = [node(*p) for p in pts]
        if closed:
            ids.append(ids[0])
        nds = "".join(f'<nd ref="{i}"/>' for i in ids)
        tg = "".join(f'<tag k="{k}" v="{v}"/>' for k, v in tags.items())
        ways.append(f'<way id="{wid}" version="1">{nds}{tg}</way>')

    way(1, [(17.0, 50.0), (17.0015, 50.0), (17.0015, 50.001), (17.0, 50.001)], {"natural": "water"}, closed=True)
    way(2, [(17.01, 50.0), (17.0105, 50.0), (17.0105, 50.0002), (17.01, 50.0002)], {"natural": "water"}, closed=True)
    way(3, [(17.02, 50.0), (17.03, 50.0)], {"waterway": "ditch"})
    way(4, [(17.04, 50.0), (17.05, 50.01)], {"waterway": "river"})
    way(5, [(17.06, 50.0), (17.07, 50.0)], {"highway": "track"})
    p = tmp_path / "t.osm"
    p.write_text('<?xml version="1.0"?><osm version="0.6">' + "".join(nodes) + "".join(ways) + "</osm>")
    return p


def test_read_pbf_classifies_and_drops_small(tmp_path):
    gdf = fw.drop_small_water(fw.read_pbf(_osm_xml(tmp_path), (16.9, 49.9, 17.2, 50.2)))
    kinds = sorted(zip(gdf["kind"], gdf.geom_type))
    assert kinds == [("ditch", "LineString"), ("water", "LineString"), ("water", "MultiPolygon")]


def test_regions_for_uses_cached_poly(tmp_path, monkeypatch):
    for name in fw.REGIONS:
        (tmp_path / f"{name}.poly").write_text(POLY if name == "opolskie" else POLY.replace("17.0", "27.0").replace("18.0", "28.0"))
    assert fw.regions_for(box(17.1, 50.1, 17.2, 50.2), tmp_path, session=None) == ["opolskie"]


def test_main_no_regions_returns_error(tmp_path, monkeypatch):
    area = tmp_path / "a.geojson"
    gpd.GeoDataFrame(geometry=[box(100, 10, 101, 11)], crs=4326).to_file(area)
    monkeypatch.setattr(fw, "regions_for", lambda *a, **k: [])
    assert fw.main(["--area", str(area), "--out", str(tmp_path / "w.parquet"), "--cache", str(tmp_path)]) == 1
