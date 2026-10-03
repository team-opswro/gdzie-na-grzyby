import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from pipeline.fetch_bdl import load_bdl

FIELDS = {"id": "adr_for", "sp_main": "species_cd", "sp_admix": None,
          "age": "spec_age", "hab": "site_type"}
FILTER = {"column": "area_type", "values": ["D-STAN"], "require_not_null": ["species_cd"]}
CFG = {"fields": FIELDS, "forest_filter": FILTER}


def _frame(rows, crs=4326):
    return gpd.GeoDataFrame(
        pd.DataFrame(rows),
        geometry=[box(17 + i * 0.01, 50, 17.005 + i * 0.01, 50.005) for i in range(len(rows))],
        crs=crs,
    )


ROWS = [
    {"adr_for": "02-40-1-12-363   -i   -00", "species_cd": "ŚW", "spec_age": 57,
     "site_type": "BŚW", "area_type": "D-STAN"},
    {"adr_for": "02-40-1-12-364   -a   -00", "species_cd": None, "spec_age": 0,
     "site_type": None, "area_type": "ZRĄB"},
    {"adr_for": "02-40-1-12-365   -a   -00", "species_cd": "DB.S", "spec_age": 0,
     "site_type": None, "area_type": "D-STAN"},
    {"adr_for": "02-40-1-12-366   -a   -00", "species_cd": "SO", "spec_age": 40,
     "site_type": "BMW", "area_type": "PLANT NAS"},
]


def test_load_bdl_maps_and_filters(tmp_path):
    _frame(ROWS[:2]).to_file(tmp_path / "a.gpkg", driver="GPKG")
    g = load_bdl(tmp_path, CFG)
    assert list(g.columns[:5]) == ["id", "sp_main", "sp_admix", "age", "hab"]
    assert len(g) == 1
    assert g.crs.to_epsg() == 4326 and g.loc[0, "sp_main"] == "SW"
    assert g.loc[0, "id"] == "02-40-1-12-363-i-00"
    assert g.loc[0, "hab"] == "BSW" and g.loc[0, "age"] == 57
    assert g.loc[0, "sp_admix"] == ()
    assert str(g["age"].dtype) == "Int64"


def test_load_bdl_geojson_reprojects_and_dedupes(tmp_path):
    a = _frame(ROWS[:1])
    a.to_file(tmp_path / "a.geojson", driver="GeoJSON")
    a.to_file(tmp_path / "b.geojson", driver="GeoJSON")      # ten sam adres w drugim pliku
    _frame(ROWS[2:3]).to_crs(2180).to_file(tmp_path / "c.gpkg", driver="GPKG")
    g = load_bdl(tmp_path, CFG)
    assert len(g) == 2
    assert g["id"].is_unique
    assert g.crs.to_epsg() == 4326
    assert g.loc[g["sp_main"] == "DB", "hab"].isna().all()
    assert g.geometry.iloc[0].bounds[0] < 18          # współrzędne w stopniach


def test_load_bdl_rejects_non_forest_type(tmp_path):
    _frame(ROWS[3:4]).to_file(tmp_path / "a.gpkg", driver="GPKG")
    assert len(load_bdl(tmp_path, CFG)) == 0
