# J. Usprawnienia aplikacji — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** parkingi z OSM na mapie, „słabe strony siedliska” w popupie, praca offline (PWA), stan ładowania rankingu i tytuł „Gdzie na grzyby?”.

**Architecture:** `pipeline/fetch_parkings.py` (Overpass) → `parkingi.geojson` → warstwa `parkingi` w `lasy.pmtiles`; `build_tiles` dopisuje `hl_<gatunek>` z rejestru czynników; w `web/` nowa warstwa i popup parkingu, teksty `hl_*`, service worker (klasyczny `sw.js` + testowalny `sw-core.js`), manifest PWA, stan ładowania.

**Tech Stack:** Python 3 (requests, geopandas, pytest + responses), plain ES modules, MapLibre, Cache API, `node --test` (+ `vm` dla `sw-core.js`).

**Spec:** `docs/superpowers/specs/2026-10-03-j-aplikacja-usprawnienia-design.md`

**Zależność:** Task 4 (`hl_*`) wymaga rejestru czynników (plan H Task 1) i czynników z planów F/I; pozostałe zadania są niezależne.

## Global Constraints

- Komentarze, komunikaty, teksty UI, commity po polsku (`feat(pipeline): …`, `feat(web): …`).
- Overpass: `https://overpass-api.de/api/interpreter`, `User-Agent: gdzie-na-grzyby`, kafle 0,5° bbox obszaru, `nwr["amenity"="parking"]` + `out center tags;`, pauza ≥ 5 s między kaflami, 429/504 → 30 s backoff, maks. 3 próby; cache `pipeline/data/raw/osm/parking_<lat>_<lon>.json`.
- Filtr parkingów: odrzucone `access ∈ {private, no, customers, permit}`, `parking ∈ {underground, multi-storey, rooftop}`; zostają punkty ≤ 300 m od wydzieleń (EPSG:2180).
- `parkingi.geojson`: punkty, atrybuty `osm` (`"n123"`/`"w123"`/`"r123"`), opcjonalnie `name`, `fee` (`"yes"`/`"no"`); w GeoJSONSeq `"tippecanoe": {"minzoom": 11}`.
- `hl_<gatunek>`: najsłabszy czynnik spośród `HABITAT_FACTORS` bez `partner`, gdy wartość < 0.8 i `h_<gatunek>` ≥ 20; teksty `HAB_LIM_TEXT` dosłownie wg spec §3.
- SW: cache `grzyby-shell-<N>`, `grzyby-data` (limit 3000), `grzyby-base` (limit 2000); network-first 4 s dla `config.json`, `manifest.json`, `live/pogoda.json`; cache-first dla `/v/<build>/` (Range: klucz `URL#range=<nagłówek>`, 206 zapisane jako 200 z `Content-Range`, odtwarzane jako 206); stale-while-revalidate dla kafli OSM/GUGiK; reszta bez cache. `sw.js` z `Cache-Control: no-cache`.
- Manifest: `name` „Gdzie na grzyby?”, `short_name` „Grzyby”, `display: standalone`.
- Tytuł: `<title>Gdzie na grzyby?</title>`.
- Testy: `.venv/bin/pytest -q`, `node --test web/tests/*.test.js`.

## Review Focus

1. **Odpowiedź 206 bez nagłówka `Content-Range` lub żądanie Range do pliku spoza `/v/<build>/`** — SW przepuszcza bez cache, nie zapisuje uszkodzonego wpisu. Test w Task 5.
2. **Nowy build danych (inny `<build>` w manifeście) przy pełnym `grzyby-data`** — stare wpisy usuwane od najstarszych, nowe pliki pobierane z sieci. Test w Task 5.
3. **Zmiana `sw.js` (nowa wersja powłoki)** — `activate` usuwa stare `grzyby-shell-*`, ale nie `grzyby-data`/`grzyby-base`. Test w Task 5.
4. **Parking typu `way`/`relation` bez `center`** — pominięty, bez wyjątku. Test w Task 1.
5. **Kliknięcie w miejsce, gdzie parking leży na wydzieleniu** — otwiera się popup parkingu, nie wydzielenia. Test w Task 3.

---

### Task 1: Pobieranie parkingów (`pipeline/fetch_parkings.py`)

**Files:**
- Create: `pipeline/fetch_parkings.py`, `tests/test_fetch_parkings.py`, `tests/fixtures/overpass_parking.json`

**Interfaces:**
- Produces:
  - `OVERPASS_URL`, `TILE_DEG = 0.5`, `MAX_DIST_M = 300`, `DEFAULT_OUT = DATA_DIR / "parkingi.geojson"`, `DEFAULT_CACHE = DATA_DIR / "raw" / "osm"`
  - `tiles_for_bounds(bounds) -> list[tuple[float, float, float, float]]` — (south, west, north, east) kafli 0,5° wyrównanych do siatki 0,5°.
  - `query(bbox) -> str` — tekst zapytania Overpass QL (`[out:json][timeout:90];nwr["amenity"="parking"](s,w,n,e);out center tags;`).
  - `fetch_tile(bbox, cache_dir, *, refresh=False, session=None, sleep=time.sleep) -> list[dict]`
  - `elements_to_gdf(elements: list[dict]) -> gpd.GeoDataFrame` — punkt z `lat`/`lon` (node) lub `center` (way/relation; brak → pominięty); filtr `access`/`parking`; deduplikacja po `osm`.
  - `near_forest(parkings: gpd.GeoDataFrame, stands: gpd.GeoDataFrame, max_dist_m=MAX_DIST_M) -> gpd.GeoDataFrame` — `sjoin_nearest(max_distance=...)` w EPSG:2180.
  - `main(argv=None) -> int` — `--area`, `--parquet`, `--out`, `--cache`, `--refresh`; wypisuje liczby przed/po filtrach.

- [ ] **Step 1: Testy**

```python
def test_tiles_cover_bounds():                  # (17.2, 49.4, 18.1, 50.2) -> kafle od (49.0,17.0) do (50.0,18.0) włącznie, krok 0.5
def test_query_text():                          # zawiera '"amenity"="parking"' i 'out center tags;'
def test_elements_filters_and_centers():        # node ok; way z center ok; way bez center pominięty; access=private odrzucony; parking=underground odrzucony
def test_near_forest_filter():                  # parking 100 m od lasu zostaje, 1 km odrzucony
def test_fetch_tile_cache_and_retry(tmp_path):  # 429 potem 200 -> 1 sleep(30), wynik; drugi przebieg bez żądań
def test_main_writes_geojson(tmp_path, monkeypatch):  # atrybuty osm/name/fee
```

- [ ] **Step 2: Uruchom** `.venv/bin/pytest tests/test_fetch_parkings.py -q` — FAIL.
- [ ] **Step 3: Implementacja** wg Interfaces (wzorzec HTTP jak `pipeline/fetch_reserves.py`).
- [ ] **Step 4: Uruchom** `.venv/bin/pytest -q` — PASS; potem naprawdę: `.venv/bin/python -m pipeline.fetch_parkings` — oczekiwane: `pipeline/data/parkingi.geojson`, liczby przed/po filtrach na stdout (zapisać do opisu commita). Odmowa Overpass po 3 próbach → zapisać w ledgerze i kontynuować (build działa bez pliku).
- [ ] **Step 5: Commit** `feat(pipeline): parkingi przy lasach z OpenStreetMap`

---

### Task 2: Warstwa `parkingi` w kafelkach

**Files:**
- Modify: `pipeline/build.py`, `pipeline/build_tiles.py` (nowe `write_parkings_seq`), `docs/data/api.md`
- Test: `tests/test_build.py`, `tests/test_build_tiles.py`

**Interfaces:**
- Produces: `write_parkings_seq(gdf, path)` — GeoJSONSeq z `"tippecanoe": {"minzoom": 11}`; `run(..., parkings_path: Path | None = DATA_DIR / "parkingi.geojson")` — warstwa `parkingi` w `tippecanoe_cmd` tylko gdy plik istnieje; `build.json` → `counts.parkings`.

- [ ] **Step 1: Testy**

```python
def test_parkings_layer_only_when_file_exists(tmp_path):   # z plikiem: "-L" "parkingi:…" w poleceniu; bez: brak
def test_parkings_seq_minzoom(tmp_path):                   # każda linia ma "tippecanoe": {"minzoom": 11} i properties osm
```

- [ ] **Step 2–4:** FAIL → implementacja → `.venv/bin/pytest -q` PASS; `api.md`: warstwa `parkingi` (atrybuty `osm`, `name?`, `fee?`, od zoomu 11, źródło OSM/ODbL).
- [ ] **Step 5: Commit** `feat(pipeline): warstwa parkingów w lasy.pmtiles`

---

### Task 3: Parkingi na mapie

**Files:**
- Modify: `web/js/map.js` (warstwa + ikona), `web/js/popup.js` (`renderParking`), `web/js/ui.js` (klik)
- Test: `web/tests/map.test.js`, `web/tests/popup.test.js`

**Interfaces:**
- Produces:
  - `parkingIcon(size = 24) -> {width, height, data}` — biały kwadrat z zaokrągleniem, granatowe „P” rysowane pikselowo (bez canvasu, jak `hatchPattern`, testowalne w Node).
  - warstwa `{ id: "parkingi", type: "symbol", source: "lasy", "source-layer": "parkingi", minzoom: 11, layout: { "icon-image": "parking", "icon-allow-overlap": true } }` dodawana na końcu `addForestLayers`.
  - `createMap(..., { onParkingClick })` — klik na `parkingi` ma pierwszeństwo przed `lasy-fill` (sprawdzenie `queryRenderedFeatures` po warstwie parkingów w handlerze kliknięcia).
  - `renderParking(props, lngLat) -> HTMLElement` — „Parking”, `name` jeśli jest, „płatny”/„bezpłatny” wg `fee`, `actionLinks(lat, lng)`.

- [ ] **Step 1: Testy**

```js
test("parkingIcon ma wymiary i nieprzezroczyste piksele", ...)
test("addForestLayers dodaje warstwę parkingi od zoomu 11", ...)   // na stubie mapy z istniejących testów
test("renderParking: nazwa, płatny, Prowadź", ...)
test("klik: parking ma pierwszeństwo przed wydzieleniem", ...)      // stub queryRenderedFeatures zwraca oba
```

- [ ] **Step 2–4:** FAIL → implementacja → `node --test web/tests/*.test.js` PASS.
- [ ] **Step 5: Commit** `feat(web): parkingi na mapie`

---

### Task 4: Słabe strony siedliska (`hl_<gatunek>`)

**Files:**
- Modify: `pipeline/build_tiles.py` (`compute_features`, `write_geojsonseq`), `web/js/popup.js`, `docs/data/api.md`
- Test: `tests/test_build_tiles.py`, `web/tests/popup.test.js`

**Interfaces:**
- Consumes: `habitat_components`, `HABITAT_FACTORS` (plany H/F/I).
- Produces:
  - `HL_THRESHOLD = 0.8`, `HL_MIN_H = 20`; `weakest_factor(components: dict[str, float]) -> str | None` — min po kluczach ≠ `"partner"`, `None` gdy min ≥ 0.8; remis → pierwszy w kolejności `HABITAT_FACTORS`.
  - `compute_features` dodaje kolumny `hl_<k>` (cache jak dla `h`), `write_geojsonseq` zapisuje je tylko gdy `h_<k> ≥ HL_MIN_H` i wartość nie jest `None`.
  - `HAB_LIM_TEXT` (spec §3, dosłownie, z prefiksem „Ogranicza siedlisko: …”) w `popup.js`; w trybie jednego gatunku linia pod tabelą „Siedlisko”, gdy `props["hl_" + species]` ma znany kod.

- [ ] **Step 1: Testy**

```python
def test_weakest_factor():            # {"partner": 0.2, "habitat": 1.0, "veg": 0.7, "age": 0.9} -> "veg"; wszystkie ≥ 0.8 -> None; remis veg/moist 0.7 -> pierwszy wg HABITAT_FACTORS
def test_hl_written_only_above_min_h(tmp_path):   # h 15 + veg 0.7 -> brak hl_; h 50 -> hl_kurka == "veg"
```
```js
test("popup: tekst słabej strony siedliska", ...)   // props hl_kurka "veg" -> „Ogranicza siedlisko: gęste runo/zadarnienie”
test("popup: nieznany kod hl_ pomijany", ...)
```

- [ ] **Step 2–4:** FAIL → implementacja → oba zestawy testów PASS.
- [ ] **Step 5: Commit** `feat: słabe strony siedliska w popupie`

---

### Task 5: Praca offline (PWA)

**Files:**
- Create: `web/sw-core.js`, `web/sw.js`, `web/manifest.webmanifest`, `web/icons/icon.svg`, `web/tests/sw.test.js`, `docs/offline.md`
- Modify: `web/index.html` (`<link rel="manifest">`, `theme-color`), `web/js/ui.js` (rejestracja, baner offline), konfiguracja nginx w `docker/` (`location = /sw.js { add_header Cache-Control "no-cache"; }`)

**Interfaces:**
- Produces (`self.SWCore` w `web/sw-core.js`, klasyczny skrypt):
  - `SHELL_VERSION` (liczba), `SHELL_CACHE = "grzyby-shell-" + SHELL_VERSION`, `DATA_CACHE = "grzyby-data"`, `BASE_CACHE = "grzyby-base"`, `LIMITS = {data: 3000, base: 2000}`, `NETWORK_TIMEOUT_MS = 4000`, `SHELL_FILES` (jawna lista plików powłoki).
  - `strategyFor(url: string, method: string, scope: string) -> "network-first" | "cache-first" | "swr" | "pass"` — `GET` tylko; `config.json`/`manifest.json`/`live/pogoda.json` → network-first; ścieżka zawierająca `/v/<build>/` (regex `/\/v\/[^/]+\//`) → cache-first; hosty `tile.openstreetmap.org`, `mapy.geoportal.gov.pl` → swr; pliki powłoki → cache-first; reszta → pass.
  - `cacheKey(url: string, range: string | null) -> string` — `range` ? `url + "#range=" + range` : `url`.
  - `trimPlan(keysOldestFirst: string[], limit: number) -> string[]` — klucze do usunięcia.
  - `staleShellCaches(names: string[]) -> string[]` — `grzyby-shell-*` ≠ `SHELL_CACHE`.
  - `web/sw.js`: `importScripts("sw-core.js")`; `install` (precache `SHELL_FILES`, `skipWaiting`), `activate` (usuń `staleShellCaches`, `clients.claim`), `fetch` wg `strategyFor`; Range: odpowiedź 206 z `Content-Range` zapisywana jako `new Response(body, {status: 200, headers: {..., "X-Content-Range": …}})` pod `cacheKey`, odtwarzana jako 206 z `Content-Range`; 206 bez `Content-Range` → bez zapisu.
  - `ui.js`: rejestracja `navigator.serviceWorker.register("sw.js")` gdy `"serviceWorker" in navigator && location.protocol !== "file:"`; baner „Tryb offline — dane z <data>” gdy `navigator.onLine === false` po załadowaniu pogody (data z `generated_at`, format jak `aboutForecastText`).

- [ ] **Step 1: Testy** (`web/tests/sw.test.js`, `vm.runInNewContext` z `{ self: {} }`)

```js
test("strategyFor: pogoda network-first w trybach data/, /dane/ i bucket", ...)
test("strategyFor: pliki wersji cache-first, podkład swr, POST pass, nieznane pass", ...)
test("cacheKey z Range i bez", ...)
test("trimPlan usuwa najstarsze ponad limit", ...)             // 3005 kluczy, limit 3000 -> 5 pierwszych
test("staleShellCaches nie rusza danych i podkładu", ...)      // ["grzyby-shell-1","grzyby-shell-2","grzyby-data","grzyby-base"] przy wersji 2 -> ["grzyby-shell-1"]
test("SHELL_FILES istnieją na dysku", ...)                     // każdy plik z listy jest w web/
```

- [ ] **Step 2: Uruchom** `node --test web/tests/sw.test.js` — FAIL.
- [ ] **Step 3: Implementacja** wg Interfaces; `node --check web/sw.js web/sw-core.js`; `docs/offline.md` — jak działa, limity, wyłącznik (zastąpienie `sw.js` wersją z `self.registration.unregister()` i podbicie `SHELL_VERSION`).
- [ ] **Step 4: Uruchom** `node --test web/tests/*.test.js` — PASS.
- [ ] **Step 5: Commit** `feat(web): praca offline — service worker i manifest PWA`

---

### Task 6: Stan ładowania rankingu i tytuł

**Files:**
- Modify: `web/js/ui.js` (`updateRanking`), `web/index.html` (`<title>`)
- Test: `web/tests/ranking.test.js` (lub nowy test funkcji wydzielonej z `updateRanking`)

**Interfaces:**
- Produces: `renderLoading(listEl)` (eksport z `web/js/ranking.js`) — `aria-busy="true"` i jeden `<li class="empty">Ładowanie…</li>`; `updateRanking` woła ją przed `await centroids.rowsNear`, a po wyniku/błędzie ustawia `aria-busy="false"`; `<title>Gdzie na grzyby?</title>`.

- [ ] **Step 1: Testy**

```js
test("renderLoading ustawia aria-busy i komunikat", ...)
test("index.html ma tytuł Gdzie na grzyby?", ...)   // odczyt pliku, regex na <title>
```

- [ ] **Step 2–4:** FAIL → implementacja → `node --test web/tests/*.test.js` PASS.
- [ ] **Step 5: Commit** `feat(web): stan ładowania rankingu i tytuł „Gdzie na grzyby?”`
