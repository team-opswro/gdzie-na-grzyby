# I. Teren: TWI i ekspozycja z NMT — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `python -m pipeline.terrain` liczy dla wydzieleń TWI, nachylenie i wystawę z Copernicus GLO-30 do `pipeline/data/terrain.parquet`; klasy `twi_class` i `exposure` wchodzą do `h` jako czynniki z mechanizmu F.

**Architecture:** `pipeline/terrain.py` dzieli się na czyste funkcje rastrowe (numpy + pysheds; testowane na syntetycznych DEM) i część I/O (pobieranie kafli, mozaika, rzutowanie rasterio, statystyki strefowe rasterstats, zapis parquet). `load_stands` dołącza parquet, jeśli istnieje; `Stand` i `species.yaml` dostają dwa czynniki tablicowe.

**Tech Stack:** Python 3, numpy, rasterio, pysheds, rasterstats, geopandas, pytest + responses.

**Spec:** `docs/superpowers/specs/2026-10-03-i-teren-nmt-design.md`

**Zależność:** plan F (Task 1–2: `TABLE_FACTORS`, `factor_value`, `Stand` z polami opcjonalnymi, `stand_from_row`).

## Global Constraints

- Komentarze, komunikaty, commity po polsku (`feat(pipeline): …`).
- Źródło: `https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM/Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM.tif`; 404 → kafel pominięty z ostrzeżeniem; cache `pipeline/data/raw/dem/`.
- Raster roboczy: EPSG:2180, piksel 30 m, bilinear, bbox obszaru + bufor 2 km; plik pośredni `pipeline/data/build/dem_2180.tif`.
- TWI = `ln(a / tan β)`, `a = (akumulacja + 1) × 30`, `tan β ≥ tan(0.1°)`.
- Wystawa 0–360°, 0 = N, zgodnie z ruchem wskazówek; średnia kołowa przez `sin`/`cos`.
- Klasy: `twi_class` ∈ `DRY`/`MID`/`WET` wg tercyli mediany TWI po wszystkich wydzieleniach; `exposure = "S_STEEP"` gdy nachylenie > 10° i wystawa ∈ [135°, 225°], inaczej `"OTHER"`.
- Czynniki: `factors_default.twi: {}`, `factors_default.exposure: {S_STEEP: 0.85, OTHER: 1.0}`; nadpisania `kozlarz.twi: {DRY: 0.85}`, `maslak.twi` i `kurka.twi: {WET: 0.85}`.
- Brak `terrain.parquet` → czynniki 1.0, build działa jak dziś.
- Atrybucja (dosłownie): „Copernicus DEM GLO-30 © DLR e.V. 2010–2014 i © Airbus Defence and Space GmbH 2014–2018, dostarczone w ramach programu Copernicus”.
- Testy: `.venv/bin/pytest -q`.

## Review Focus

1. **Wydzielenie mniejsze niż piksel 30 m** — `all_touched=True` daje co najmniej jeden piksel; wydzielenie bez pikseli pominięte, a nie `NaN` w klasach. Test w Task 2.
2. **Piksele NoData na brzegu mozaiki / brak kafla (404)** — nie zaniżają TWI sąsiadów do `-inf`; statystyki strefowe ignorują NoData. Test w Task 1.
3. **Wystawa wokół północy** (350° i 10°) — średnia ~0°, nie 180°. Test w Task 1.
4. **Teren idealnie płaski** (tan β = 0) — TWI skończone. Test w Task 1.
5. **Brak pamięci przy całym obszarze** — wariant przetwarzania po nadleśnictwach z progami tercyli liczonymi na końcu (spec §3). Pomiar w Task 4; wybór wariantu = ruling w ledgerze.

---

### Task 1: Czyste funkcje rastrowe

**Files:**
- Create: `pipeline/terrain.py` (sekcja funkcji czystych)
- Modify: `pipeline/requirements.txt` (`rasterio`, `pysheds`, `rasterstats`)
- Test: `tests/test_terrain.py`

**Interfaces:**
- Produces:
  - `PIXEL_M = 30.0`, `MIN_SLOPE_DEG = 0.1`, `STEEP_DEG = 10.0`, `SOUTH = (135.0, 225.0)`
  - `slope_aspect(dem: np.ndarray, pixel: float = PIXEL_M, nodata: float | None = None) -> tuple[np.ndarray, np.ndarray]` — nachylenie (stopnie) i wystawa (0–360, 0 = N, wiersz 0 = północ rastra); NoData → `nan`.
  - `flow_accumulation(dem: np.ndarray, nodata: float | None = None) -> np.ndarray` — pysheds (`Grid`/`Raster` z macierzy, `fill_pits`, `fill_depressions`, `resolve_flats`, `flowdir` D8, `accumulation`); NoData → `nan`.
  - `twi(acc: np.ndarray, slope_deg: np.ndarray, pixel: float = PIXEL_M) -> np.ndarray`
  - `circular_mean_deg(sin_mean: float, cos_mean: float) -> float` (0–360)
  - `twi_classes(values: np.ndarray) -> tuple[list[str], tuple[float, float]]` — klasy i progi tercyli (`np.nanquantile` 1/3, 2/3; `≤ t1` → `DRY`, `> t2` → `WET`).
  - `exposure_class(slope_deg: float, aspect_deg: float) -> str`

- [ ] **Step 1: Testy**

```python
def test_valley_twi_higher_than_ridge():        # DEM 50×50 w kształcie V (dolina w kolumnie 25): twi[25, 25] > twi[25, 2]
def test_flat_dem_finite_twi():                 # stała wysokość -> np.isfinite(twi).all()
def test_aspect_south_and_north_planes():       # płaszczyzna opadająca na południe -> aspect ~180 (±1); na północ -> ~0 lub ~360
def test_circular_mean_wraps_north():           # sin/cos średnie z 350° i 10° -> wynik < 1 lub > 359
def test_nodata_does_not_poison_neighbours():   # DEM z ramką NoData -> twi w środku skończone, na ramce nan
def test_twi_classes_terciles():                # values 1..9 -> progi (3.67, 6.33), klasy [DRY]*3 + [MID]*3 + [WET]*3
def test_exposure_class():                      # (15, 180) S_STEEP; (5, 180) OTHER; (15, 0) OTHER; (15, 135) S_STEEP; (15, 226) OTHER
```

- [ ] **Step 2: Uruchom** `.venv/bin/pip install rasterio pysheds rasterstats && .venv/bin/pytest tests/test_terrain.py -q` — FAIL (brak funkcji).
- [ ] **Step 3: Implementacja** wg Interfaces. Jeśli pysheds nie działa z bieżącym numpy (błąd importu/API) — ruling: własna implementacja D8 + akumulacja (priority-flood wypełnienie, kierunek do najniższego z 8 sąsiadów, akumulacja w kolejności malejącej wysokości) w tym samym interfejsie.
- [ ] **Step 4: Uruchom** `.venv/bin/pytest -q` — PASS.
- [ ] **Step 5: Commit** `feat(pipeline): TWI, nachylenie i wystawa z modelu terenu`

---

### Task 2: Kafle GLO-30, mozaika, statystyki strefowe, CLI

**Files:**
- Modify: `pipeline/terrain.py` (I/O + `main`)
- Modify: `pipeline/Dockerfile` (nic, jeśli wheels instalują się z `requirements.txt`; inaczej `libgdal` — ruling)
- Test: `tests/test_terrain.py`

**Interfaces:**
- Consumes: Task 1; `pipeline.ingest.DATA_DIR`, `DEFAULT_PARQUET` (geometrie wydzieleń), `pipeline/data/obszar.geojson`.
- Produces:
  - `DEM_URL` (szablon z Global Constraints), `DEFAULT_OUT = DATA_DIR / "terrain.parquet"`, `DEFAULT_CACHE = DATA_DIR / "raw" / "dem"`, `BUFFER_M = 2000`
  - `tile_names(bounds: tuple[float, float, float, float]) -> list[tuple[int, int]]` — pary `(lat, lon)` całkowitych stopni kafli przecinających bbox (lon, lat).
  - `download_tiles(tiles, cache_dir, *, refresh=False, session=None) -> list[Path]` — stream do pliku `.part` → rename; 404 → ostrzeżenie (stderr), pominięcie.
  - `build_dem(paths: list[Path], area_2180, out_tif: Path) -> None` — `rasterio.merge` → `reproject` do EPSG:2180, piksel 30 m, bbox obszaru + `BUFFER_M`.
  - `zonal(stands_2180: gpd.GeoDataFrame, twi, slope, aspect, transform, nodata) -> pd.DataFrame` — `rasterstats.zonal_stats(all_touched=True)`: mediana `twi`, średnia `slope`, średnie `sin`/`cos` wystawy → `aspect`; kolumny `prefix`, `a_i_num`, `twi`, `slope`, `aspect`; wydzielenia bez pikseli pominięte.
  - `main(argv=None) -> int` — opcje `--refresh`, `--out`, `--cache`, `--parquet`, `--area`; zapis parquet z kolumnami + `twi_class`, `exposure`; progi tercyli w metadanych parquet (`pyarrow` schema metadata `{"twi_terciles": "[t1, t2]", "dem": "GLO-30"}`); podsumowanie na stdout (liczba wydzieleń, udział pokrytych, progi).

- [ ] **Step 1: Testy**

```python
def test_tile_names_for_bbox():                     # (17.2, 49.4, 19.8, 51.1) -> 3 × 3 = 9 par: lat 49..51, lon 17..19
def test_download_skips_404_and_caches(tmp_path):   # responses: N50_E018 200, N50_E019 404 -> 1 plik; drugi przebieg 0 żądań
def test_zonal_two_polygons_epsg2180():             # syntetyczny raster 2180 + 2 kwadraty -> mediany zgodne z wartościami, kolumny jak w Interfaces
def test_tiny_polygon_gets_pixel():                 # poligon 5×5 m -> wiersz obecny (all_touched)
def test_main_writes_parquet_with_metadata(tmp_path, monkeypatch):  # monkeypatch download/build_dem na mały syntetyczny raster -> parquet z twi_class/exposure i metadanymi
```

- [ ] **Step 2: Uruchom** `.venv/bin/pytest tests/test_terrain.py -q` — FAIL.
- [ ] **Step 3: Implementacja** wg Interfaces.
- [ ] **Step 4: Uruchom** `.venv/bin/pytest -q` — PASS.
- [ ] **Step 5: Commit** `feat(pipeline): pipeline.terrain — kafle GLO-30 i statystyki dla wydzieleń`

---

### Task 3: Czynniki terenowe w modelu

**Files:**
- Modify: `forecast/species.py` (`TABLE_FACTORS` + `"twi"`, `"exposure"`), `pipeline/habitat.py` (`Stand.twi_class`, `Stand.exposure`, `factor_value` dla nowych tabel, `stand_from_row`), `pipeline/ingest.py` (`load_stands(..., terrain_path=DEFAULT_TERRAIN)`), `pipeline/build_tiles.py` (przekazanie pól), `pipeline/build.py` (`build.json` → `terrain`), `species.yaml`, `docs/data/api.md`, `web/index.html` (atrybucja w „Źródła i licencje”)
- Test: `tests/test_habitat.py`, `tests/test_ingest.py`, `tests/test_build.py`, `tests/test_species.py`

**Interfaces:**
- Consumes: `terrain.parquet` (Task 2), mechanizm F.
- Produces:
  - `DEFAULT_TERRAIN = DATA_DIR / "terrain.parquet"` w `pipeline/ingest.py`; `load_stands` — left join po (`prefix`, `a_i_num`), brak pliku → kolumny `twi_class`, `exposure` = `None`.
  - `Stand.twi_class: str | None = None`, `Stand.exposure: str | None = None`; czynniki tablicowe o tych samych nazwach co pola (`twi` ← `twi_class`, `exposure` ← `exposure`).
  - `build.json` → `"terrain": {"twi_terciles": [t1, t2], "dem": "GLO-30"}` gdy plik istnieje (czytane z metadanych parquet).

- [ ] **Step 1: Testy**

```python
def test_twi_factor_kozlarz_dry():           # Stand(..., twi_class="DRY") -> czynnik twi == 0.85 dla kozlarza, 1.0 dla borowika
def test_exposure_factor_all_species():      # exposure="S_STEEP" -> 0.85 dla każdego gatunku
def test_load_stands_without_terrain(tmp_path):   # terrain_path nieistniejący -> kolumny None
def test_load_stands_with_terrain(tmp_path):      # parquet z 1 wierszem -> klasy dołączone do właściwego wydzielenia
def test_build_json_terrain_meta(tmp_path):       # z parquetem -> meta["terrain"]["twi_terciles"] == [t1, t2]; bez -> brak klucza
```

- [ ] **Step 2: Uruchom** — FAIL.
- [ ] **Step 3: Implementacja** wg Interfaces; atrybucja w `web/index.html` i `docs/data/api.md` (tekst z Global Constraints).
- [ ] **Step 4: Uruchom** `.venv/bin/pytest -q && node --test web/tests/*.test.js` — PASS.
- [ ] **Step 5: Commit** `feat(pipeline): wilgotność topograficzna i ekspozycja w ocenie siedliska`

---

### Task 4: Przebieg na prawdziwych danych i walidacja

- [ ] **Step 1:** `.venv/bin/python -m pipeline.terrain` (sieć: ~10–15 kafli po 25–40 MB). Mierzyć szczytowe RSS (`/usr/bin/time -v`). Oczekiwane: `pipeline/data/terrain.parquet` z ≥ 99% wydzieleń `stands.parquet`. Przy błędzie pamięci (dostępne ~6 GB) — ruling: przetwarzanie po nadleśnictwach (obrys `nadlesnictwa.geojson` + bufor 2 km, TWI per nadleśnictwo, statystyki tylko dla wydzieleń wewnątrz obrysu, tercyle na końcu z całości) i dopisanie testu dla wariantu.
- [ ] **Step 2:** `.venv/bin/python -m pipeline.validate --no-weather --compare pipeline/data/walidacja/walidacja-baza.json` (wymaga planu H). Czynnik `twi` lub `exposure`, którego ablacja nie obniża AUC żadnego gatunku z wynikiem → tabela neutralna w `species.yaml`; powtórzyć raport.
- [ ] **Step 3:** `.venv/bin/pytest -q` — PASS.
- [ ] **Step 4: Commit** (jeśli zmieniono `species.yaml`) `chore(pipeline): czynniki terenowe po walidacji` z liczbami AUC; w opisie także liczba wydzieleń z danymi terenu, progi tercyli i szczytowa pamięć.
