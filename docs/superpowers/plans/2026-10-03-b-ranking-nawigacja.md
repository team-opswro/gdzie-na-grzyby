# B. Ranking i nawigacja — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ranking pokazuje 10 różnych oddziałów z nazwami leśnictwa i nadleśnictwa, odległością i kierunkiem; popup ma „Prowadź” i „Udostępnij miejsce”; topbar ma „Udostępnij”; promień rankingu do wyboru; GPS jako przełącznik.

**Architecture:** Pipeline zapisuje mały słownik nazw `web/data/nazwy.json` (nadleśnictwa z `bdl_fields.yaml`, leśnictwa z BDL `lesnictwa`). Frontend: czysty moduł `names.js` (nazwy, linki nawigacji), `ranking.js` grupuje po oddziale i liczy kierunek, `hash.js` dostaje `r` i `w`, `ui.js` spina panel, udostępnianie i GPS.

**Tech Stack:** Python 3 (requests, pytest), ES modules, `node:test`, MapLibre GL JS.

**Spec:** `docs/superpowers/specs/2026-10-03-b-ranking-nawigacja-design.md`

## Global Constraints

- `web/data/nazwy.json`: `{ "nadl": { "RR-NN": "<nazwa>" }, "lesn": { "RR-NN-O-LL": "<nazwa>" } }`; `nadl` z `pipeline/bdl_fields.yaml` (`districts[].prefix` → `name`); `lesn` z OGC API `https://ogcapi.bdl.lasy.gov.pl/collections/lesnictwa/items` (pola `forest_range_name`, `adress_forest`), per nadleśnictwo `filter=adress_forest LIKE '<prefix>%'`, `filter-lang=cql-text`, stronicowanie jak `fetch_bdl` (limit 1000, do niepełnej strony); klucz = usuń białe znaki, weź pierwsze 4 segmenty po `-` (`"02-04-1-07-      -    -"` → `"02-04-1-07"`).
- Klucz oddziału = pierwsze 5 segmentów `id` (`02-04-1-07-368-a-00` → `02-04-1-07-368`); numer oddziału = 5. segment.
- `formatPlace` → „Oddz. 368 · Leśn. Zieleniec · Nadl. Brzeg” (brakujące części pomijane); bez nazw → „Oddz. 368 · 02-04-1-07”.
- Kierunki (8): „płn.”, „płn.-wsch.”, „wsch.”, „płd.-wsch.”, „płd.”, „płd.-zach.”, „zach.”, „płn.-zach.” (sektory po 45°, „płn.” = azymut [337,5; 22,5)).
- Wiersz rankingu: linia 1 `[wynik][strzałka trendu] Oddz. … · Leśn. … · Nadl. …`; linia 2 `4,2 km płn.-wsch. · 3 wydz.` (`count`; także „1 wydz.”).
- Linki: „Prowadź” → `https://www.google.com/maps/dir/?api=1&destination=<lat>,<lon>`; „OSM” → `https://www.openstreetmap.org/directions?route=%3B<lat>%2C<lon>`; współrzędne 5 miejsc po przecinku; `target="_blank" rel="noopener"`.
- Hash: `r ∈ {5,10,20,40}`, domyślnie 20 (nie zapisywany); `w` = id wydzielenia, walidacja `^[0-9A-Za-z-]{1,40}$`, obecny tylko gdy popup otwarty.
- Udostępnianie: `navigator.share({ title, url })`; brak API lub błąd ≠ `AbortError` → `navigator.clipboard.writeText` + toast „Skopiowano link” (2 s, `role="status"`); brak schowka → `prompt()` z linkiem. „Udostępnij miejsce” ustawia `c` = punkt, `z = max(z, 15)`, `w = id` przed udostępnieniem.
- Panel: „Top 10 w promieniu” + `<select>` 5/10/20/40 km (klik w select nie zwija panelu); podpis „od Twojej lokalizacji” / „od środka mapy”; ◎ z `aria-pressed`; błąd lokalizacji → wyłączony + podpis „Brak zgody na lokalizację — ranking od środka mapy”.
- Komunikat pustego rankingu używa bieżącego promienia („Brak miejsc o dodatnim wyniku w promieniu 10 km”).
- Popup: nagłówek `formatPlace`, pod nim małą czcionką pełne `id`; wiersz akcji „Prowadź” · „OSM” · „Udostępnij miejsce” (nie dla rezerwatów).
- `nazwy.json` ładowany niezależnie (`Promise.allSettled`); awaria nie blokuje mapy.
- Testy: `.venv/bin/pytest -q`, `node --test web/tests/*.test.js`.

## Review Focus

- `nazwy.json` niedostępny → ranking i popup z samym adresem, bez wyjątków → test w Task 2 (`formatPlace` bez nazw) i Task 4 (`loadData`).
- Link z `w=` do wydzielenia, którego nie ma w widoku (np. zoom za mały) → mapa tylko wycentrowana, bez błędu → weryfikacja w Task 6.
- Oddział z literą w numerze (`201B`) i adresy RDLP Łódź/Wrocław → poprawny klucz i numer → test w Task 2.
- GPS: wyłączenie przełącznika przywraca ranking od środka mapy i reakcję na przesuwanie → weryfikacja w Task 6.
- Udostępnianie anulowane przez użytkownika (`AbortError`) → brak toastu i brak kopiowania → test w Task 4 (`shareUrl` z mockiem).

---

### Task 1: `pipeline/fetch_names.py` i `web/data/nazwy.json`

**Files:** Create `pipeline/fetch_names.py`, `tests/test_fetch_names.py`, `tests/fixtures/bdl_lesnictwa.json`, `web/data/nazwy.json`; Modify `README.md` (krok po `fetch_bdl`).

**Interfaces — Produces:** `range_key(adress_forest: str) -> str | None` (None gdy < 4 segmentów); `build_names(districts: list[dict], features_by_prefix: dict[str, list[dict]]) -> dict`; CLI `python -m pipeline.fetch_names [--out web/data/nazwy.json]` (zapis atomowy `.tmp` + `replace`; błąd → stderr, `return 1`, istniejący plik nietknięty).

- [ ] **Step 1: Failing tests:** `range_key("02-04-1-07-      -    -") == "02-04-1-07"`, `range_key("13-02-1-03-63    -b   -00") == "13-02-1-03"`, `range_key("02-04") is None`; `build_names` z fixture: `nadl == {"02-04": "Brzeg", ...}` dla podanych districts, `lesn` zawiera klucze z fixture, pomija rekordy bez nazwy; `main` z zamockowanym `_get_json` zapisuje plik; pusta odpowiedź dla wszystkich → `return 1` i plik nietknięty.
- [ ] **Step 2–4:** FAIL → implement (import `_get_json` z `pipeline.fetch_bdl` do przestrzeni modułu) → `.venv/bin/pytest -q` PASS.
- [ ] **Step 5:** Uruchom naprawdę `.venv/bin/python -m pipeline.fetch_names` (27 nadleśnictw, kilka zapytań). Sprawdź: `nadl` ma 27 kluczy, `lesn` > 300 kluczy, ≥ 95% prefiksów `RR-NN-O-LL` z `web/data/centroidy.json` ma nazwę (wypisz odsetek). Plik < 50 kB.
- [ ] **Step 6:** Commit `feat(pipeline): nazwy nadleśnictw i leśnictw (nazwy.json)`.

---

### Task 2: `web/js/names.js`

**Files:** Create `web/js/names.js`, `web/tests/names.test.js`

**Interfaces — Produces:** `oddzKey(id) -> string | null`; `placeName(id, nazwy) -> { oddz, lesn: string|null, nadl: string|null, lesnKey }`; `formatPlace(id, nazwy) -> string`; `navUrls(lat, lon) -> { google, osm }`.

- [ ] **Step 1: Failing tests:** `oddzKey("02-04-1-07-368-a-00") === "02-04-1-07-368"`; `oddzKey("06-01-2-13-201B-b-00") === "06-01-2-13-201B"`; `oddzKey("x") === null`; `formatPlace` pełne, bez leśnictwa („Oddz. 368 · Nadl. Brzeg”), `nazwy = null` → „Oddz. 368 · 02-04-1-07”; `navUrls(50.123456, 17.9)` → dokładne URL-e z Global Constraints (`50.12346,17.90000`).
- [ ] **Step 2–4:** FAIL → implement → `node --test web/tests/*.test.js` PASS.
- [ ] **Step 5:** Commit `feat(web): names.js (nazwy miejsc, linki nawigacji)`.

---

### Task 3: Ranking grupowany po oddziale z kierunkiem

**Files:** Modify `web/js/ranking.js`, `web/tests/ranking.test.js`

**Interfaces — Consumes:** `oddzKey` (Task 2). **Produces:** `bearing(origin, point) -> string` (8 nazw z Global Constraints); `topN(centroids, pogoda, species, dayIdx, origin, radiusKm = 20, n = 10)` → `[{ key, best: { id, lat, lon, cell, h, score }, count, distanceKm, bearing }]`; sortowanie: `best.score` malejąco, potem `key` rosnąco; `best` = najwyższy wynik w oddziale (remis: mniejsze `id`); `count` = wydzielenia oddziału z wynikiem > 0 w promieniu; `distanceKm` (0,1 km) i `bearing` liczone do `best`; id bez klucza oddziału → grupa jednoelementowa z kluczem = `id`.

- [ ] **Step 1: Failing tests:** dwa wydzielenia jednego oddziału → jedna grupa z `count 2`, `best` wyższy; remis wyników → mniejsze `id`; 8 kierunków (punkty N, NE, E, SE, S, SW, W, NW od origin); promień i `n` jak dotąd (dostosuj istniejące testy do nowego kształtu).
- [ ] **Step 2–4:** FAIL → implement → PASS (popraw `ui.js` tylko na tyle, by nadal działał z nowym kształtem: `r.best.*`, w tym strzałka trendu z A liczona z `r.best.cell`/`r.best.h` i `flyToRow(r.best)` — pełny wiersz w Task 5).
- [ ] **Step 5:** Commit `feat(web): ranking grupowany po oddziale z kierunkiem`.

---

### Task 4: Hash `r`/`w`, ładowanie nazw, udostępnianie (logika)

**Files:** Modify `web/js/hash.js`, `web/js/data.js`; Create `web/js/share.js`; Tests `web/tests/hash.test.js`, `web/tests/data.test.js`, `web/tests/share.test.js`

**Interfaces — Produces:**
- `RADII = [5, 10, 20, 40]`; `parseHash` zwraca dodatkowo `radius` (domyślnie 20) i `place` (id lub `undefined`); `formatHash({..., radius, place})` dopisuje `&r=` gdy ≠ 20 i `&w=` gdy `place` poprawne; kolejność parametrów: `s, d, z, c, b, r, w`.
- `loadData(base)` zwraca dodatkowo `nazwy` (`null` przy błędzie).
- `share.js`: `shareUrl(url, title, { nav = navigator, notify, promptFn = globalThis.prompt }) -> Promise<"shared"|"copied"|"prompted"|"aborted">`.

- [ ] **Step 1: Failing tests:** `parseHash("#r=10&w=02-04-1-07-368-a-00")` → `radius 10`, `place` = id; `r=7` → 20; `w=<script>` → `undefined`; `formatHash` z `radius 20` bez `r`; roundtrip; `loadData` z `nazwy.json` OK / błąd → `nazwy: null` (pozostałe pola bez zmian); `shareUrl`: share OK → „shared”; share rzuca `AbortError` → „aborted”, `notify` nie wołane; brak share, jest clipboard → „copied” + `notify("Skopiowano link")`; brak obu → „prompted”.
- [ ] **Step 2–4:** FAIL → implement → PASS (popraw istniejące `deepEqual` w `hash.test.js` o `radius: 20, place: undefined`).
- [ ] **Step 5:** Commit `feat(web): hash r/w, nazwy w loadData, logika udostępniania`.

---

### Task 5: UI — wiersze rankingu, popup z nazwami i akcjami, panel, GPS, udostępnianie

**Files:** Modify `web/js/ui.js`, `web/js/popup.js`, `web/index.html`, `web/css/app.css`; Test `web/tests/popup.test.js`

**Interfaces — Consumes:** Tasks 2–4. **Produces:** `popup.js`: `renderPopup(props, ctx)` z `ctx` rozszerzonym o `nazwy`, `lngLat`, `onShare`; nagłówek i wiersz akcji wg Global Constraints; `actionLinks(lat, lon) -> HTMLElement`. `ui.js`: stan `radius`, `place`; `gps` jako przełącznik; toast; `#share` w topbarze; po starcie z `place` — po pierwszym `idle` z danymi szukaj wydzielenia (`queryRenderedFeatures` w punkcie `c`, potem w całym widoku) i otwórz popup, inaczej nic.

- [ ] **Step 1: Failing test** (`popup.test.js`): eksportowana funkcja `rankLabel(group, nazwy) -> { line1, line2 }` (tekst bez wyniku/strzałki) daje „Oddz. 368 · Leśn. Zieleniec · Nadl. Brzeg” i „4,2 km płn.-wsch. · 3 wydz.”.
- [ ] **Step 2–4:** FAIL → implement → `node --test web/tests/*.test.js` PASS.
- [ ] **Step 5:** UI wg Global Constraints (panel, select promienia, podpis źródła, ◎ `aria-pressed`, toast, `#share`, popup: nagłówek, `id` małą czcionką, akcje; zamknięcie popupu usuwa `w` z hasha). Przyciski ≥ 40 px; topbar mieści się w 375 px (gatunek, dni, ◎, ⤴). Na ekranach ≤ 700 px po otwarciu popupu przesuń mapę (`map.panTo`/`easeTo` z `offset`) tak, by punkt popupu był w górnej ~1/3 widoku i popup nie chował się pod zwiniętym panelem „Top 10” (znany problem z A).
- [ ] **Step 6:** Commit `feat(web): ranking z nazwami, Prowadź, udostępnianie, promień i przełącznik GPS`.

---

### Task 6: Weryfikacja end-to-end

- [ ] **Step 1:** Stos Compose lokalnie + Playwright (headless): ranking ma nazwy i kierunki, 10 różnych oddziałów; zmiana promienia zmienia listę i `r=` w hashu; popup ma nagłówek z nazwami, „Prowadź” z poprawnym URL; „Udostępnij miejsce” (w Playwright: `navigator.share` niedostępny → schowek z uprawnieniem albo `prompt`) daje URL z `w=`; otwarcie tego URL w nowej karcie otwiera popup tego samego wydzielenia; `w=` dla wydzielenia spoza widoku → brak błędu; GPS: zasymuluj geolokalizację (`context.setGeolocation`), włącz → podpis „od Twojej lokalizacji”, wyłącz → „od środka mapy” i ranking reaguje na przesunięcie; 375 px — topbar i panel bez nakładania (zrzuty); konsola bez błędów JS.
- [ ] **Step 2:** `down -v`, usuń override; pełne testy; poprawki jako `fix: …`.
