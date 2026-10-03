# A. Popup i prognoza — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Popup pokazuje realne wartości pogody (mm, °C, wilgotność), zdanie o czynniku ograniczającym, wykres wyniku na 7 dni z przełączaniem dnia i strzałkę trendu; ranking też pokazuje trend.

**Architecture:** `forecast` liczy dodatkowo wartości pogody per komórka (`wx`) i kod czynnika ograniczającego per gatunek (`lim`), a `pogoda.json` obejmuje wczoraj + 7 dni. Frontend dostaje czysty moduł `chart.js` (dane wykresu, trend, rysowanie SVG) i rozbudowany `popup.js`; działa także ze starym formatem pliku.

**Tech Stack:** Python 3 (pytest, jsonschema), MapLibre GL JS, ES modules, `node:test`.

**Spec:** `docs/superpowers/specs/2026-10-03-a-popup-prognoza-design.md`

## Global Constraints

- `days`: 8 dat, `days[0]` = wczoraj, `days[1..7]` = dziś … +6; wszystkie serie per gatunek mają 8 elementów; `forecast/run.py`: `DAYS = 7`, `PAST_DAYS = 1`.
- `wx` (najwyższy poziom): `{ "<cell>": { "rain_mm": [8], "soil_t": [8], "soil_m": [8] } }`; `rain_mm` = suma `precip[i-k]` dla `k ∈ RAIN_WINDOW` (5..21), bez wag, indeksy < 0 pomijane, 0,1 mm; `soil_t` = `_mean_back(soil_temp, i, TEMP_LOOKBACK)`, fallback `soil_temp[i]`, 0,1 °C; `soil_m` = `_mean_back(soil_moisture, i, MOISTURE_LOOKBACK)`, fallback `soil_moisture[i]`, 0,001.
- `lim` per gatunek: `"dry" | "dry_soil" | "cold" | "hot" | "season" | null`; `LIM_THRESHOLD = 0.8`; kandydaci = składowe `< 0.8`; wybór najmniejszej, remis w kolejności `season`, `temp`, `rain`; `temp` → `cold` gdy średnia temp. gleby `< sp.temp[1]`, inaczej `hot`; `rain` → `dry_soil` gdy zadziałała kara `MOISTURE_PENALTY`, inaczej `dry`.
- Schemat: `days`, `series` `minItems = maxItems = 8`; `$defs.lim`; `species.required` += `lim`; wymagany `wx`; `rain_mm ≥ 0`, `soil_m ∈ [0, 1]`.
- Teksty `lim`: `dry` „Ogranicza: za mało deszczu”, `dry_soil` „Ogranicza: przesuszona gleba”, `cold` „Ogranicza: za zimna gleba”, `hot` „Ogranicza: za ciepła gleba”, `season` „Ogranicza: poza sezonem”.
- Wiersze `wx`: „Deszcz (5–21 dni wcześniej): 34,2 mm”, „Gleba: 11,3 °C, wilgotna” (przecinek dziesiętny); wilgotność: `< SOIL_DRY = 0.15` „sucha”, `< SOIL_WET = 0.30` „umiarkowana”, wyżej „wilgotna”.
- `<details>` „Szczegóły modelu” z dotychczasowymi procentami (opad, temperatura, sezon).
- Trend: próg ±5 pkt; `dir ∈ {"up","down","flat",null}`; strzałki ↑ ↓ →; `title` np. „+12 względem poprzedniego dnia”; „Szczyt: sob. (72)” gdy późniejszy dzień przewyższa bieżący o ≥ 5.
- Wykres: 7 słupków (dni dostępne), inline SVG, kolor `COLORS.classes[cls]`, brak danych = pusty kontur, wybrany dzień obrysowany, skrót dnia („pn”, „wt”, „śr”, „czw”, „pt”, „sob”, „nd”), wartość nad słupkiem; słupek = `<g role="button" tabindex="0" aria-label="sob. 4 paź: 72">`, klik/Enter → `onSelect(idx)`.
- Zgodność: stary `pogoda.json` (7 dni, bez `wx`/`lim`) → popup z procentami, bez zdania `lim`, bez trendu dla `pogoda.days[0]`.
- Rezerwat (`props.rez`) — bez wyniku, wykresu, trendu (jak dziś).
- Testy: `.venv/bin/pytest -q`, `node --test web/tests/*.test.js`.

## Review Focus

- Stary `pogoda.json` w wolumenie (do najbliższego crona) → mapa, popup i ranking działają, bez wyjątków → test w Task 3 (`weatherFor`/`chartData`/`trend` na fixture v1).
- Dzień „dziś” wypada po północy, a `pogoda.json` jest z wczoraj (dni przesunięte) → `availableDays` odfiltrowuje przeszłe; trend używa `idx - 1` w `pogoda.days`, nie w `availableDays` → test w Task 4.
- Komórka bez danych dla części dni (`w[i] == null`) → słupek pusty, trend `null` → test w Task 4.
- Kliknięcie słupka zmienia dzień na mapie i popup zostaje otwarty dla tego samego wydzielenia → weryfikacja ręczna w Task 6.
- Brak `wx` dla komórki (nowy format, ale komórka spoza `wx`) → bez wierszy realnych wartości, bez błędu → test w Task 3.

---

### Task 1: Model — wartości pogody i czynnik ograniczający

**Files:** Modify `forecast/model.py`; Test `tests/test_model.py`

**Interfaces — Produces:**
- `WeatherValues` dataclass `(rain_mm: float, soil_t: float, soil_m: float)`; `weather_values(s: DailySeries, i: int) -> WeatherValues` (bez zaokrągleń)
- `_rain_parts(s, i, sp) -> tuple[float, bool]` (`(rain, penalized)`); `rain_factor` zwraca `_rain_parts(...)[0]` (sygnatura bez zmian)
- `LIM_THRESHOLD = 0.8`; `limiting_factor(comps: WeatherComponents, s: DailySeries, i: int, sp: Species) -> str | None`

- [ ] **Step 1: Failing tests**: `test_weather_values_window` (opad 1 mm/dzień, `i=30` → `rain_mm == 17.0`; `i=10` → suma tylko istniejących indeksów 5..10 = 6.0), `test_weather_values_means` (soil_t/soil_m = średnie z lookbacków), `test_limiting_factor_none_when_all_high`, `test_limiting_factor_cold_vs_hot` (temp. gleby 3 °C → `cold`; 30 °C → `hot` dla borowika `temp: [6,12,20,26]`), `test_limiting_factor_dry_vs_dry_soil` (wilgotność 0.05 → `dry_soil`; 0.3 → `dry`), `test_limiting_factor_season`, `test_limiting_factor_tie_order` (season == temp == 0.5 → `season`).
- [ ] **Step 2:** `.venv/bin/pytest tests/test_model.py -q` → FAIL (ImportError).
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** `.venv/bin/pytest -q` → PASS.
- [ ] **Step 5:** Commit `feat(forecast): realne wartości pogody i czynnik ograniczający`.

---

### Task 2: `pogoda.json` — wczoraj, `wx`, `lim`, schemat

**Files:** Modify `forecast/run.py`, `schema/pogoda.schema.json`, `tests/test_run.py`; Create `tests/fixtures/pogoda_v1.json` (kopia obecnego `tests/fixtures/pogoda.json` sprzed zmiany, `git mv` niedozwolone — skopiuj); Modify `tests/fixtures/pogoda.json` (nowy format, wygenerowany przez `build_payload` z serii testowych, 2 komórki z obecnej fixture: zachowaj ich identyfikatory `506_178`, `507_178`; `days` od `2026-10-02`)

**Interfaces — Consumes:** Task 1. **Produces:** format z Global Constraints; `build_payload(cells, series, species, today, now)` bez zmian sygnatury.

- [ ] **Step 1: Failing tests** w `tests/test_run.py`: `days` ma 8 dat, `days[0] == "2026-10-02"`, `days[1] == "2026-10-03"`; każda seria ma 8 elementów; `p["wx"]["506_178"]` ma klucze `rain_mm, soil_t, soil_m` po 8 liczb; `lim` obecne per gatunek i w zbiorze dozwolonych; walidacja schematem; `test_missing_yesterday_raises_value_error` (seria zaczyna się dziś → `ValueError`); fixture `tests/fixtures/pogoda.json` waliduje się nowym schematem; `pogoda_v1.json` **nie** waliduje się (sanity).
- [ ] **Step 2:** FAIL. **Step 3:** Implement (zaokrąglenia jak w Global Constraints, `lim` bez zaokrągleń). **Step 4:** `.venv/bin/pytest -q` → PASS (popraw istniejące asercje „7 dni” na nowe wartości).
- [ ] **Step 5:** `node --test web/tests/*.test.js` — testy JS używają `tests/fixtures/pogoda.json`; jeśli któryś zależy od 7 dni, popraw go w tym zadaniu (fixture ma teraz wczoraj na indeksie 0). → PASS.
- [ ] **Step 6:** Commit `feat(forecast): pogoda.json z wczorajszym dniem, wx i lim`.

---

### Task 3: `data.js` — odczyt nowych pól ze zgodnością wstecz

**Files:** Modify `web/js/data.js`; Test `web/tests/data.test.js`

**Interfaces — Produces:** `weatherFor(pogoda, cell, species, dayIdx)` → `{ w, rain, temp, season, lim, wx }` lub `null`; `lim` = `sp.lim?.[dayIdx] ?? null`; `wx` = `{ rain_mm, soil_t, soil_m }` z `pogoda.wx?.[cell]` dla `dayIdx` lub `null`.

- [ ] **Step 1: Failing tests**: na nowej fixture `lim` i `wx` zgodne z plikiem; na `pogoda_v1.json` `lim === null`, `wx === null`, reszta jak dawniej; komórka nieobecna w `wx` → `wx === null`. Istniejący test „weatherFor returns fixture values” rozszerz o `lim`, `wx`.
- [ ] **Step 2–4:** FAIL → implement → `node --test web/tests/*.test.js` PASS.
- [ ] **Step 5:** Commit `feat(web): weatherFor z lim i wx`.

---

### Task 4: `chart.js` — dane wykresu, trend, SVG

**Files:** Create `web/js/chart.js`; Test `web/tests/chart.test.js`

**Interfaces — Consumes:** `availableDays`, `weatherFor`, `score`, `scoreClass` (`data.js`), `COLORS` (`map.js`). **Produces:**
- `chartData(pogoda, cell, species, h, todayIso) -> [{ date, idx, score: number|null, cls: number|null }]` (dni z `availableDays`, maks. 7)
- `trend(pogoda, cell, species, h, dayIdx) -> { dir, delta, peak: { idx, date, score } | null }` (`dayIdx` = indeks w `pogoda.days`)
- `DOW = ["nd","pn","wt","śr","czw","pt","sob"]`; `renderChart(data, selectedIdx, onSelect) -> SVGElement` (DOM tylko wewnątrz funkcji)

- [ ] **Step 1: Failing tests**: `chartData` pomija dni przeszłe (na nowej fixture z `todayIso = days[1]` → 7 elementów, pierwszy `idx === 1`), brak `w` → `score null, cls null`; `trend` z `dayIdx = 1` używa wczoraj (`idx 0`); `dayIdx = 0` → `dir null`; progi: `delta 5 → "up"`, `4 → "flat"`, `-5 → "down"`; `peak` tylko gdy późniejszy dzień ≥ bieżący + 5; stara fixture: `trend(..., 0)` → `dir null`, bez wyjątku.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Commit `feat(web): moduł chart.js (dane wykresu, trend, SVG)`.

---

### Task 5: Popup, ranking i przełączanie dnia z wykresu

**Files:** Modify `web/js/popup.js`, `web/js/ui.js`, `web/css/app.css`; Test `web/tests/popup.test.js`

**Interfaces — Consumes:** Tasks 3–4. **Produces:**
- `popup.js`: `LIM_TEXT` (mapa kod → tekst), `moistureLabel(m) -> string`, `formatWx(wx) -> { rain: string, soil: string }` (teksty z Global Constraints), `trendArrow(dir) -> string` (`"↑"|"↓"|"→"|""`); `renderPopup(props, ctx)` z `ctx = { pogoda, species, dayIdx, todayIso, onDaySelect }` (pogoda może być `null`)
- `ui.js`: `showPopup` zapamiętuje `{props, lngLat}`; `onDaySelect(idx)` ustawia `state.day` na pozycję `idx` w `days`, `refresh()`, po czym ponownie otwiera popup dla zapamiętanego wydzielenia; wiersz rankingu ma strzałkę trendu po wyniku (`trend` z wiersza centroidu: `h = row[col]`, komórka `row[3]`)

- [ ] **Step 1: Failing tests** (`popup.test.js`): `LIM_TEXT` (5 tekstów dokładnie), `moistureLabel(0.149) === "sucha"`, `(0.15) === "umiarkowana"`, `(0.30) === "wilgotna"`; `formatWx({rain_mm: 34.2, soil_t: 11.3, soil_m: 0.31})` → `{ rain: "Deszcz (5–21 dni wcześniej): 34,2 mm", soil: "Gleba: 11,3 °C, wilgotna" }`; `trendArrow`.
- [ ] **Step 2–4:** FAIL → implement (kolejność treści popupu wg spec §3.2; `<details>` dla procentów; dla `props.rez` bez zmian względem dziś) → `node --test web/tests/*.test.js` PASS.
- [ ] **Step 5:** CSS: wykres mieści się w popupie 280 px; słupki ≥ 24 px szerokości dotyku; `<details>` czytelne.
- [ ] **Step 6:** Commit `feat(web): popup z realną pogodą, wykresem 7 dni i trendem`.

---

### Task 6: Weryfikacja end-to-end

- [ ] **Step 1:** `.venv/bin/python -m forecast.run --grid web/data/grid.json --out web/data/live/pogoda.json` (Open-Meteo, kilka zapytań) → plik waliduje się, ma 8 dni.
- [ ] **Step 2:** Stos Compose lokalnie (README, override portu 8080; `forecast` wygeneruje ten sam format) i Playwright: popup wydzielenia pokazuje zdanie `lim` (o ile nie `null`), wiersze mm/°C, wykres 7 słupków, strzałkę; klik w słupek zmienia `#day-label` i `d=` w hashu, popup nadal otwarty; ranking ma strzałki; podmiana `web/data/live/pogoda.json` na `tests/fixtures/pogoda_v1.json`-podobny stary plik (z dzisiejszymi datami) → popup z procentami, 0 błędów konsoli; szerokość 375 px — popup mieści wykres; konsola bez błędów.
- [ ] **Step 3:** `down -v`, usuń override; pełne testy; commit ewentualnych poprawek (`fix: …`).
