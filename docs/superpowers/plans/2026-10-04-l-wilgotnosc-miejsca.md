# Plan L: wilgotność miejsca — implementacja

Spec: `docs/superpowers/specs/2026-10-04-l-wilgotnosc-miejsca-design.md`. Wykonanie samodzielne (TDD per zadanie).

1. `species.yaml` + `forecast/species.py`: sekcja `water:`, pole `partner_weights`; borowik: `veg: {}`, `density`,
   wagi partnerów. `pipeline/habitat.py`: wagi w `partner_score`. Testy: `test_species.py`, `test_habitat.py`.
2. `forecast/model.py: wet_adjust` + `tests/fixtures/wet_cases.json` + `tests/test_model.py`.
3. `pipeline/terrain.py`: `tpi_raster`, kolumna `tpi` w `zonal`. Test na syntetycznym DEM.
4. `pipeline/fetch_water.py` (Overpass, kafle, cache) + testy z atrapą sesji.
5. `pipeline/wetness.py`: składniki, percentyle, `wet`, `wl` → `wetness.parquet`. Testy jednostkowe.
6. `pipeline/ingest.load_stands` + `build_tiles` (atrybuty `wet`/`wl`, kolumna `extra` w centroidach) + `build.py`.
7. `pipeline/validate.py --wet` (AUC w obrębie kratki i dnia) + test.
8. web: `adjustW`, `weatherFor(..., wet)`, `bestFor`, mapa (wyrażenie), ranking, wykres, popup; testy node na
   `wet_cases.json`.
9. `docs/data/api.md`, teksty UI.
10. Przebieg na danych: `fetch_water`, `terrain`, `wetness`, `validate`, build w kontenerze,
    `scripts/check_wet_case.py`; potem merge do `main`, push, publish.
