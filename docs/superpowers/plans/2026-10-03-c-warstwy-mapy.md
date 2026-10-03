# C. Warstwy mapy — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rezerwaty przyrody są na mapie szare i kreskowane, opisane nazwą, wykluczone z rankingu; użytkownik może przełączyć podkład na ortofotomapę lub mapę topograficzną; jest link do aktualnych zakazów wstępu.

**Architecture:** Nowy krok pipeline `fetch_reserves` zapisuje rezerwaty GDOŚ do `pipeline/data/rezerwaty.geojson`; `build_tiles` oznacza wydzielenia atrybutem `rez` (flaga BDL `forest_fun` lub punkt reprezentatywny w poligonie GDOŚ), pomija je w `centroidy.json` i dokłada do PMTiles warstwę `rezerwaty`. Frontend (`map.js`) ma gałąź koloru dla `rez`, warstwy kreskowania/obrysu rezerwatów i trzy rastrowe podkłady przełączane widocznością; stan podkładu w hashu (`b=`).

**Tech Stack:** Python 3 (geopandas, shapely, requests, pytest), tippecanoe, MapLibre GL JS + PMTiles (vendor), Node `node:test`.

**Spec:** `docs/superpowers/specs/2026-10-03-c-warstwy-mapy-design.md`

## Global Constraints

- Źródło rezerwatów: `https://sdi.gdos.gov.pl/wfs`, `typeNames=GDOS:Rezerwaty`, `outputFormat=application/json`, `srsName=EPSG:4326`, pole nazwy `nazwa` (zweryfikowane 2026-10-03; 109 obiektów w bbox obszaru).
- Wydzielenie jest rezerwatowe, gdy `forest_fun` zaczyna się od `REZ` (`REZ`, `REZ CZ`) **lub** jego punkt reprezentatywny (`lat`/`lon`) leży w poligonie GDOŚ; nazwa z GDOŚ ma pierwszeństwo, bez nazwy → `"rezerwat"`.
- Kolor rezerwatu `COLORS.reserve = "#757575"`, krycie `FILL_OPACITY.reserve = 0.5`; obrys rezerwatu `#6a1b9a`, 1,5 px; kreskowanie: wzór 8×8 px generowany w kodzie (bez plików graficznych).
- **Bez etykiet tekstowych** na mapie (wymagałyby zewnętrznego serwera fontów `glyphs`); nazwa rezerwatu tylko w popupie.
- Tekst popupu (dokładnie): `Rezerwat przyrody „<nazwa>” — zbieranie grzybów jest co do zasady zabronione.`; dla `rez == "rezerwat"`: `Rezerwat przyrody — zbieranie grzybów jest co do zasady zabronione.`
- Link zakazów (stopka i każdy popup wydzielenia): tekst `Sprawdź aktualne zakazy wstępu (BDL)`, URL `https://zakazywstepu.bdl.lasy.gov.pl/zakazy/`.
- Legenda: wpis `rezerwat — zbiór zabroniony`.
- Podkłady, parametr hasha `b ∈ {osm, orto, topo}`, domyślny `osm` (nie zapisywany w hashu):
  - `osm`: `https://tile.openstreetmap.org/{z}/{x}/{y}.png` (bez zmian),
  - `orto`: `https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMS/StandardResolution?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=Raster&STYLES=&CRS=EPSG:3857&BBOX={bbox-epsg-3857}&WIDTH=256&HEIGHT=256&FORMAT=image/png`,
  - `topo`: jak `orto`, host/ścieżka `https://mapy.geoportal.gov.pl/wss/service/img/guest/TOPO/MapServer/WMSServer` (GetCapabilities nie deklaruje 3857, ale GetMap w 3857 działa — sprawdzone 2026-10-03; jeśli przestanie: OpenTopoMap `https://{a,b,c}.tile.opentopomap.org/{z}/{x}/{y}.png`).
- Atrybucja podkładu w stopce: `osm` „© OpenStreetMap” (z linkiem jak dziś), `orto` „Ortofotomapa: GUGiK (geoportal.gov.pl)”, `topo` „Mapa topograficzna: GUGiK (geoportal.gov.pl)”. Stała atrybucja: „Rezerwaty: GDOŚ”.
- Na `orto` warstwa `lasy-line`: `line-color #ffffff`, `line-opacity 0.7`; na pozostałych jak dziś (`#3e2723`, 0,6).
- Testy: `.venv/bin/pytest -v`, `node --test web/tests/*.test.js` (pliki jawnie).

## Review Focus

- Rezerwat na gruntach spoza Lasów Państwowych (brak wydzieleń BDL) — kliknięcie w jego obszar ma pokazać popup z nazwą (warstwa `rezerwaty-fill` jest klikalna) → test w Task 5 (`reserveText`) + weryfikacja ręczna w Task 7.
- GDOŚ zwraca pustą kolekcję lub błąd → `fetch_reserves` kończy się błędem i **nie nadpisuje** istniejącego pliku → test w Task 2.
- Zły parametr `b` w hashu (`b=satelita`) → podkład `osm`, bez błędu → test w Task 4.
- Przeglądarka ma w cache (max-age 1 dzień) stary `lasy.pmtiles` bez warstwy `rezerwaty` i atrybutu `rez` → mapa działa jak dziś, bez błędów w konsoli; ranking już bez rezerwatów (`centroidy.json` ma `no-cache`) → weryfikacja ręczna w Task 7.
- Wydzielenie zaczyna się w rezerwacie, ale jego punkt reprezentatywny leży poza nim i nie ma flagi BDL → nie jest oznaczone; akceptowane (spec), test dokumentujący zachowanie w Task 3.

---

### Task 1: Spike — źródło czasowych zakazów wstępu

**Files:**
- Create: `docs/data/zakazy.md`

Ograniczone czasowo rozpoznanie (maks. ~1 h), bez kodu produkcyjnego.

- [ ] **Step 1:** Otwórz `https://zakazywstepu.bdl.lasy.gov.pl/zakazy/` w przeglądarce (DevTools → Network albo skill `claude-in-chrome`), wybierz nadleśnictwo z obszaru (np. Opole), zapisz wszystkie zapytania XHR/fetch: URL, metoda, parametry, format odpowiedzi.
- [ ] **Step 2:** Ustal i zapisz w `docs/data/zakazy.md`: (a) czy endpoint działa bez sesji/ciasteczek (`curl`), (b) czy odpowiedź ma geometrię albo klucz (adres leśny / leśnictwo / nadleśnictwo), (c) daty obowiązywania zakazu, (d) czy regulamin BDL (`/portal/regulamin`) dopuszcza automatyczne pobieranie, (e) werdykt: **pozytywny** (opis kontraktu danych dla osobnego planu „7b”) albo **negatywny** (zostaje tylko link).
- [ ] **Step 3: Commit**

```bash
git add docs/data/zakazy.md
git commit -m "docs: rozpoznanie źródła zakazów wstępu (BDL)"
```

Wynik pozytywny **nie** rozszerza tego planu — implementacja warstwy zakazów to osobny plan po akceptacji użytkownika.

---

### Task 2: Pobieranie rezerwatów GDOŚ (`pipeline/fetch_reserves.py`)

**Files:**
- Create: `pipeline/fetch_reserves.py`
- Create: `tests/fixtures/gdos_rezerwaty.json` (2–3 obiekty z odpowiedzi WFS, w tym jeden częściowo poza obszarem, jeden całkiem poza; współrzędne skrócone)
- Test: `tests/test_fetch_reserves.py`

**Interfaces:**
- Consumes: `pipeline.fetch_bdl._get_json(session, url, params) -> dict` (retry).
- Produces:
  - `WFS_URL = "https://sdi.gdos.gov.pl/wfs"`, `TYPE_NAME = "GDOS:Rezerwaty"`, `RESERVES_PATH = pipeline/data/rezerwaty.geojson`
  - `wfs_params(bounds: tuple[float, float, float, float]) -> dict` — `bounds` = `(minx, miny, maxx, maxy)` w lon/lat; `bbox` w kolejności `miny,minx,maxy,maxx,urn:ogc:def:crs:EPSG::4326`
  - `clip_reserves(fc: dict, area) -> gpd.GeoDataFrame` — kolumny `name`, `geometry` (EPSG:4326), tylko obiekty przecinające `area`, przycięte; `ValueError`, gdy `fc` nie ma obiektów
  - CLI `python -m pipeline.fetch_reserves [--area pipeline/data/obszar.geojson] [--out pipeline/data/rezerwaty.geojson]`

- [ ] **Step 1: Write the failing tests**

```python
def test_wfs_params_axis_order():
    p = wfs_params((16.8, 49.9, 19.0, 51.3))
    assert p["typeNames"] == "GDOS:Rezerwaty" and p["outputFormat"] == "application/json"
    assert p["srsName"] == "EPSG:4326"
    assert p["bbox"] == "49.9,16.8,51.3,19.0,urn:ogc:def:crs:EPSG::4326"

def test_clip_reserves_names_and_clipping():
    fc = json.load(open(FIXTURE))
    g = clip_reserves(fc, AREA)          # AREA = box obejmujący część fixture
    assert list(g.columns) == ["name", "geometry"] and g.crs.to_epsg() == 4326
    assert "<nazwa obiektu całkiem poza>" not in set(g["name"])
    assert all(AREA.buffer(1e-9).contains(geom) for geom in g.geometry)

def test_clip_reserves_empty_raises():
    with pytest.raises(ValueError):
        clip_reserves({"type": "FeatureCollection", "features": []}, AREA)

def test_main_keeps_existing_file_on_error(tmp_path, monkeypatch):
    out = tmp_path / "rez.geojson"; out.write_text("STARE")
    monkeypatch.setattr(fetch_reserves, "_get_json", lambda *a, **k: {"features": []})
    assert fetch_reserves.main(["--area", str(AREA_FILE), "--out", str(out)]) != 0
    assert out.read_text() == "STARE"
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_fetch_reserves.py -v` — Expected: FAIL (`ModuleNotFoundError: pipeline.fetch_reserves`).
- [ ] **Step 3: Implement** `pipeline/fetch_reserves.py` — `clip_reserves`: `gpd.GeoDataFrame.from_features`, `nazwa` → `name`, `make_valid`, `gpd.clip(..., keep_geom_type=True)`, odrzuć puste. `main`: czyta obszar, `wfs_params(area.total_bounds)`, `_get_json`, `clip_reserves`, zapis przez plik `.tmp` + `replace` (jak `fetch_bdl`), na `ValueError`/`RuntimeError` komunikat na stderr i `return 1`. Wypisuje liczbę rezerwatów.
- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_fetch_reserves.py -v` — Expected: PASS.
- [ ] **Step 5: Commit**

```bash
git add pipeline/fetch_reserves.py tests/test_fetch_reserves.py tests/fixtures/gdos_rezerwaty.json
git commit -m "feat(pipeline): pobieranie rezerwatów GDOŚ"
```

---

### Task 3: Oznaczanie rezerwatów w `build_tiles`

**Files:**
- Modify: `pipeline/bdl_fields.yaml` (`fields` += `fun: forest_fun`)
- Modify: `pipeline/fetch_bdl.py` (`load_bdl`: kolumna `fun`; `OUT_COLUMNS`)
- Modify: `pipeline/build_tiles.py`
- Test: `tests/test_fetch_bdl.py`, `tests/test_build_tiles.py`

**Interfaces:**
- Consumes: `pipeline/data/rezerwaty.geojson` (Task 2: kolumny `name`, `geometry`).
- Produces:
  - `load_bdl(...)` zwraca dodatkowo kolumnę `fun: str | None` (None, gdy `fields.fun` nie skonfigurowane lub wartość pusta)
  - `mark_reserves(feats: gpd.GeoDataFrame, reserves: gpd.GeoDataFrame | None) -> gpd.GeoDataFrame` — dodaje kolumnę `rez: str | None`; brak kolumny `fun` traktowany jak same `None`
  - `write_centroids` pomija wiersze z `rez` niepustym
  - `write_geojsonseq` dodaje właściwość `rez` (gdy niepusta)
  - `write_reserves_seq(reserves: gpd.GeoDataFrame, path: Path) -> None` — GeoJSONSeq z właściwością `name`
  - `tippecanoe_cmd(out: Path, layers: dict[str, Path]) -> list[str]` — `-L <nazwa>:<plik>` dla każdej warstwy, reszta flag jak dziś (`-Z8 -z14 --drop-smallest-as-needed --force`)
  - CLI `build_tiles` dostaje `--reserves` (domyślnie `pipeline/data/rezerwaty.geojson`; brak pliku → błąd z komunikatem „uruchom python -m pipeline.fetch_reserves”)

- [ ] **Step 1: Write the failing tests**

```python
# test_fetch_bdl.py — ROWS dostają "forest_fun"; CFG fields += {"fun": "forest_fun"}
def test_load_bdl_reads_forest_function(tmp_path):
    ...  # wiersz D-STAN z forest_fun="REZ CZ"
    assert g.loc[0, "fun"] == "REZ CZ"

def test_load_bdl_without_fun_field(tmp_path):
    ...  # CFG bez klucza fun
    assert g["fun"].isna().all()

# test_build_tiles.py
RES = gpd.GeoDataFrame({"name": ["Góra Św. Anny"]}, geometry=[box(17.0, 50.0, 17.5, 50.5)], crs=4326)

def test_mark_reserves_by_polygon_and_flag():
    f = compute_features(gdf_from([sq(50.2, 17.2), sq(50.8, 17.9), sq(50.9, 17.9)]), S)
    f["fun"] = [None, "REZ", "GOSP"]
    m = mark_reserves(f, RES)
    assert list(m["rez"]) == ["Góra Św. Anny", "rezerwat", None]

def test_mark_reserves_gdos_name_wins_over_flag():
    f = compute_features(gdf_from([sq(50.2, 17.2)]), S); f["fun"] = ["REZ"]
    assert mark_reserves(f, RES).loc[0, "rez"] == "Góra Św. Anny"

def test_mark_reserves_uses_representative_point():
    # wydzielenie wchodzi w rezerwat krawędzią, punkt reprezentatywny poza nim, brak flagi → nie oznaczone
    f = compute_features(gdf_from([box(17.49, 50.2, 17.7, 50.3)]), S)
    assert mark_reserves(f, RES).loc[0, "rez"] is None

def test_mark_reserves_without_fun_column_and_reserves():
    f = compute_features(gdf_from([sq(50.2, 17.2)]), S)
    assert mark_reserves(f, None).loc[0, "rez"] is None

def test_centroids_skip_reserves(tmp_path):
    f = mark_reserves(compute_features(gdf_from([sq(50.2, 17.2), sq(50.8, 17.9)]), S), RES)
    p = tmp_path / "c.json"
    assert write_centroids(f, KEYS, p) == 1
    assert json.load(open(p))["rows"][0][0] == "id1"

def test_geojsonseq_has_rez(tmp_path): ...   # pierwszy obiekt: properties["rez"] == "Góra Św. Anny", drugi bez klucza "rez"

def test_tippecanoe_cmd_two_layers(tmp_path):
    cmd = tippecanoe_cmd(tmp_path, {"lasy": Path("a.seq"), "rezerwaty": Path("r.seq")})
    assert cmd[:3] == ["tippecanoe", "-o", str(tmp_path / "lasy.pmtiles")]
    assert "-L" in cmd and "lasy:a.seq" in cmd and "rezerwaty:r.seq" in cmd and "-l" not in cmd
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_fetch_bdl.py tests/test_build_tiles.py -v` — Expected: nowe testy FAIL (`ImportError: mark_reserves`, brak kolumny `fun`).
- [ ] **Step 3: Implement** — `load_bdl`: `fun` jak `hab` (string lub None), gdy `cols.get("fun")`. `mark_reserves`: punkty z `lat`/`lon` → `gpd.sjoin(points, reserves, predicate="within", how="left")`, pierwszy trafiony `name` na wydzielenie; w pozostałych `fun.str.startswith("REZ")` → `"rezerwat"`. `main`: wczytaj `--reserves`, `mark_reserves` po `compute_features`, `write_reserves_seq` do `build-dir/rezerwaty.geojsonseq`, `subprocess.run(tippecanoe_cmd(...), check=True)`; wypisz liczbę wydzieleń z `rez`.
- [ ] **Step 4: Run** `.venv/bin/pytest -v` — Expected: wszystkie PASS.
- [ ] **Step 5: Commit**

```bash
git add pipeline/bdl_fields.yaml pipeline/fetch_bdl.py pipeline/build_tiles.py tests/test_fetch_bdl.py tests/test_build_tiles.py
git commit -m "feat(pipeline): oznaczanie rezerwatów, warstwa rezerwaty w PMTiles"
```

---

### Task 4: Parametr podkładu w hashu

**Files:**
- Modify: `web/js/hash.js`
- Test: `web/tests/hash.test.js`

**Interfaces:**
- Produces: `BASEMAP_KEYS = ["osm", "orto", "topo"]` (eksport z `hash.js`); `parseHash(h)` zwraca dodatkowo `basemap` (zawsze, domyślnie `"osm"`); `formatHash({..., basemap})` dopisuje `&b=<key>` na końcu tylko dla `basemap` różnego od `"osm"` i niepustego.

- [ ] **Step 1: Write the failing tests** — w istniejących `deepEqual` dopisz `basemap: "osm"`; w roundtripie obiekt `s` dostaje `basemap: "osm"`, format bez zmian. Nowe:

```js
test("basemap param", () => {
  assert.equal(parseHash("#s=kurka&d=0&b=orto").basemap, "orto");
  assert.equal(parseHash("#b=satelita").basemap, "osm");
  assert.equal(formatHash({ species: "kurka", day: 0, basemap: "topo" }), "#s=kurka&d=0&b=topo");
  assert.equal(formatHash({ species: "kurka", day: 0, basemap: "osm" }), "#s=kurka&d=0");
});
```

- [ ] **Step 2: Run** `node --test web/tests/hash.test.js` — Expected: FAIL.
- [ ] **Step 3: Implement** w `web/js/hash.js`.
- [ ] **Step 4: Run** `node --test web/tests/hash.test.js` — Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(web): parametr podkładu b w hashu"` (z `web/js/hash.js`, `web/tests/hash.test.js`).

---

### Task 5: `map.js` — rezerwaty i podkłady

**Files:**
- Modify: `web/js/map.js`
- Test: `web/tests/map.test.js`

**Interfaces:**
- Consumes: `BASEMAP_KEYS` z `hash.js` (Task 4).
- Produces (eksporty `map.js`):
  - `COLORS.reserve`, `FILL_OPACITY.reserve` (wartości z Global Constraints)
  - `fillColorExpression(...)` / `fillOpacityExpression(...)` → `["case", ["has", "rez"], <reserve>, <dotychczasowe wyrażenie>]`
  - `hatchPattern(size = 8) -> { width, height, data: Uint8Array }` — RGBA, ukośne linie koloru `#424242`, tło przezroczyste
  - `BASEMAPS: { osm|orto|topo: { tiles: string[], attribution: string, maxzoom: number } }` (`osm` 19, `orto` 19, `topo` 17)
  - `lineColor(basemap) -> { color, opacity }`
  - `setBasemap(map, key)` — `visibility` warstw `base-osm`, `base-orto`, `base-topo` + paint `lasy-line` wg `lineColor`
  - `createMap(container, { ..., basemap = "osm", onReserveClick })` — źródła `base-<key>` i warstwy `base-<key>` (tylko aktywna `visible`), `map.addImage("hatch", hatchPattern())` przed warstwami używającymi wzoru (w `load`, potem `addLayer` dla `lasy-rez-hatch`), warstwy: `lasy-fill`, `lasy-rez-hatch` (`filter: ["has", "rez"]`, `fill-pattern: "hatch"`), `lasy-line`, `rezerwaty-fill` (source-layer `rezerwaty`, `#6a1b9a`, krycie 0,08), `rezerwaty-line`; klik: najpierw `lasy-fill` → `onFeatureClick`, inaczej `rezerwaty-fill` → `onReserveClick(name, lngLat)`

- [ ] **Step 1: Write the failing tests** — istniejący test „missing-cell branch” czyta bazowe wyrażenie z `c[3]`/`o[3]` (gałąź „else” nowego `case`). Nowe:

```js
test("reserve branch comes first", () => {
  for (const p of [P, null]) {
    const c = fillColorExpression(p, "borowik", 0);
    assert.deepEqual(c.slice(0, 3), ["case", ["has", "rez"], COLORS.reserve]);
    assert.equal(fillOpacityExpression(p, "borowik", 0)[2], FILL_OPACITY.reserve);
  }
  assert.ok(!COLORS.classes.includes(COLORS.reserve) && COLORS.reserve !== COLORS.noData);
});
test("hatch pattern is 8x8 RGBA with transparent and opaque pixels", () => {
  const h = hatchPattern();
  assert.equal(h.width, 8); assert.equal(h.data.length, 8 * 8 * 4);
  const alphas = new Set([...h.data].filter((_, i) => i % 4 === 3));
  assert.ok(alphas.has(0) && alphas.has(255));
});
test("basemaps", () => {
  assert.deepEqual(Object.keys(BASEMAPS), BASEMAP_KEYS);
  for (const k of ["orto", "topo"]) {
    const u = BASEMAPS[k].tiles[0];
    assert.ok(u.includes("{bbox-epsg-3857}") && u.includes("CRS=EPSG:3857") && u.includes("LAYERS=Raster"));
  }
  assert.deepEqual(lineColor("orto"), { color: "#ffffff", opacity: 0.7 });
  assert.deepEqual(lineColor("osm"), { color: "#3e2723", opacity: 0.6 });
});
```

- [ ] **Step 2: Run** `node --test web/tests/map.test.js` — Expected: FAIL.
- [ ] **Step 3: Implement** w `web/js/map.js` (bez użycia globalnych `maplibregl`/`pmtiles` poza `createMap`, żeby testy w Node działały).
- [ ] **Step 4: Run** `node --test web/tests/*.test.js` — wszystkie pliki jawnie (`data map hash ranking`), Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(web): rezerwaty na mapie i przełączane podkłady"` (z `web/js/map.js`, `web/tests/map.test.js`).

---

### Task 6: UI — popup, legenda, stopka, przełącznik podkładu

**Files:**
- Modify: `web/js/popup.js`, `web/js/ui.js`, `web/index.html`, `web/css/app.css`
- Create: `web/tests/popup.test.js`

**Interfaces:**
- Consumes: `COLORS.reserve`, `setBasemap`, `BASEMAPS`, `createMap({ basemap, onReserveClick })` (Task 5); `parseHash().basemap`, `formatHash({ basemap })` (Task 4).
- Produces:
  - `popup.js`: `ZAKAZY_URL`, `reserveText(rez: string) -> string` (teksty z Global Constraints), `renderReserve(name: string) -> HTMLElement`; `renderPopup` dla `props.rez` pokazuje ramkę `reserveText` (lewa krawędź `COLORS.reserve`) zamiast wyniku i bez wierszy pogody; każdy popup wydzielenia kończy się linkiem zakazów (`target="_blank" rel="noopener"`)
  - `ui.js`: `state.basemap`; kontrolka przełącznika (3 przyciski radiowe „Mapa”, „Satelita”, „Topo”, `role="radiogroup"`, `aria-checked`) w `#basemap` nad mapą w prawym górnym rogu pod kontrolką zoomu; zmiana → `setBasemap`, aktualizacja `#attr-base`, `writeHash`
  - `index.html`: w stopce `<span id="attr-base">`, „Rezerwaty: GDOŚ”, link zakazów; kontener `#basemap`
  - legenda: wpis `rezerwat — zbiór zabroniony` z kwadratem w kreskowanie (CSS `repeating-linear-gradient` na tle `#757575`)

- [ ] **Step 1: Write the failing test** `web/tests/popup.test.js`:

```js
test("reserveText with and without name", () => {
  assert.equal(reserveText("Góra Św. Anny"),
    "Rezerwat przyrody „Góra Św. Anny” — zbieranie grzybów jest co do zasady zabronione.");
  assert.equal(reserveText("rezerwat"),
    "Rezerwat przyrody — zbieranie grzybów jest co do zasady zabronione.");
});
test("zakazy URL", () => assert.equal(ZAKAZY_URL, "https://zakazywstepu.bdl.lasy.gov.pl/zakazy/"));
```

- [ ] **Step 2: Run** `node --test web/tests/popup.test.js` — Expected: FAIL.
- [ ] **Step 3: Implement** `reserveText`, `renderReserve`, zmiany `renderPopup` (popup.js nie może dotykać `document` przy imporcie).
- [ ] **Step 4: Run** `node --test web/tests/popup.test.js` — Expected: PASS.
- [ ] **Step 5: Implement** UI: `ui.js` (stan z hasha, `createMap({ basemap: state.basemap, onReserveClick: (name, ll) => popup z renderReserve })`, przełącznik, `#attr-base`, `writeHash` z `basemap`), `index.html`, `app.css` (przełącznik czytelny na telefonie: przyciski ≥ 40 px wysokości, nie zasłania legendy).
- [ ] **Step 6: Run** `node --test web/tests/data.test.js web/tests/hash.test.js web/tests/map.test.js web/tests/ranking.test.js web/tests/popup.test.js` — Expected: PASS.
- [ ] **Step 7: Commit** `git commit -m "feat(web): popup rezerwatu, legenda, przełącznik podkładu, link do zakazów"`.

---

### Task 7: Przebudowa danych, dokumentacja, weryfikacja w przeglądarce

**Files:**
- Create: `pipeline/data/rezerwaty.geojson`
- Modify: `web/data/lasy.pmtiles`, `web/data/centroidy.json`, `web/data/grid.json`
- Modify: `README.md`, `docs/data/bdl.md`

- [ ] **Step 1:** `.venv/bin/python -m pipeline.fetch_reserves` — Expected: komunikat z liczbą rezerwatów (> 0, rząd 50–110), plik `pipeline/data/rezerwaty.geojson` < 1 MB.
- [ ] **Step 2:** Przebuduj kafelki (polecenie `podman run ... pipeline.build_tiles` z README, z `--reserves pipeline/data/rezerwaty.geojson`). Expected: wypisana liczba wydzieleń z `rez` (rząd ≥ 500, bo sama flaga BDL daje 501), liczba centroidów mniejsza niż przed zmianą.
- [ ] **Step 3:** Sprawdź: `python3 -c "import json;d=json.load(open('web/data/centroidy.json'));print(len(d['rows']))"` vs `git show HEAD:web/data/centroidy.json | python3 -c ...` — Expected: spadek; oraz że PMTiles ma 2 warstwy (`pmtiles show web/data/lasy.pmtiles` w kontenerze pipeline lub `tippecanoe-decode`), Expected: `lasy`, `rezerwaty`.
- [ ] **Step 4:** README: krok `python -m pipeline.fetch_reserves` po `pipeline.area`, flaga `--reserves` w poleceniu build, w „Dane i licencje” wpis „Rezerwaty: Generalna Dyrekcja Ochrony Środowiska (GDOŚ), WFS sdi.gdos.gov.pl” i „Podkłady: ortofotomapa i mapa topograficzna GUGiK (geoportal.gov.pl)”. `docs/data/bdl.md`: pole `forest_fun` (`GOSP`/`REZ`/`REZ CZ`) używane do oznaczania rezerwatów.
- [ ] **Step 5:** Uruchom stos Compose lokalnie (README, override z portem 8080) i sprawdź w przeglądarce (skill `run` lub `claude-in-chrome`):
  - rezerwat (np. okolice Góry Św. Anny) szary, kreskowany, z fioletowym obrysem; klik → tekst z Global Constraints,
  - klik w obszar rezerwatu poza wydzieleniami → popup z nazwą,
  - ranking w okolicy rezerwatu nie zawiera wydzieleń rezerwatowych,
  - przełącznik: „Satelita” i „Topo” ładują kafelki, obrysy na satelicie białe, stopka zmienia atrybucję, `b=` w hashu, przeładowanie strony zachowuje podkład,
  - `#b=satelita` → mapa OSM bez błędów,
  - szerokość 375 px: przełącznik i legenda się nie nakładają,
  - konsola bez błędów.
- [ ] **Step 6: Run** pełne testy: `.venv/bin/pytest -v` i `node --test web/tests/*.test.js` (pliki jawnie) — Expected: PASS.
- [ ] **Step 7: Commit**

```bash
git add pipeline/data/rezerwaty.geojson web/data/ README.md docs/data/bdl.md
git commit -m "data: rezerwaty GDOŚ, przebudowa kafelków z warstwą rezerwatów"
```
