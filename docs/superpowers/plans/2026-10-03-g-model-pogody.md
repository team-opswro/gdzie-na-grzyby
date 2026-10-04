# G. Model pogody: bilans wodny, głębsza wilgotność, impuls temperatury, przymrozek — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `w = min(1, rain × temp × season × pulse × frost)` z bilansem wodnym i wilgotnością z dwóch warstw; nowe pola w `pogoda.json` (wstecznie zgodne) i w popupie.

**Architecture:** `forecast/weather.py` pobiera trzy nowe zmienne do `DailySeries` (pola opcjonalne); `forecast/model.py` liczy nowe składowe; `forecast/run.py` dopisuje je do `pogoda.json`; schemat i `api.md` opisują opcjonalne pola; `web/js/data.js` + `popup.js` je pokazują.

**Tech Stack:** Python 3, requests, jsonschema, pytest; plain ES modules + `node --test`.

**Spec:** `docs/superpowers/specs/2026-10-03-g-model-pogody-design.md`

## Global Constraints

- Komentarze, komunikaty, teksty UI, commity po polsku (`feat(forecast): …`, `feat(web): …`).
- Stałe: `ET_ALPHA = 0.3`, `MOISTURE_SHALLOW_WEIGHT = 0.5`, `PULSE_MAX = 0.2`, `PULSE_DROP_FULL = 3.0`, `FROST_FLOOR = 0.2`, `FROST_RECOVERY_DAYS = 7`; `DEFAULT_FROST_MIN = -2.0` w `forecast/species.py` (pole `Species.frost_min`, YAML `frost_min`).
- `ET_ALPHA = 0` musi odtwarzać dotychczasowy `rain`.
- Kolejność remisu `limiting_factor`: `season`, `frost`, `temp`, `rain`; `pulse` nigdy nie ogranicza.
- `WeatherComponents` pola: `w, rain, temp, season, pulse, frost` (raport H iteruje `dataclasses.fields`).
- Nowe pola w schemacie opcjonalne (stary `pogoda.json` nadal się waliduje); `pulse` z zakresem 1–1.2.
- Teksty UI: `LIM_TEXT.frost = "Ogranicza: niedawny przymrozek"`, wiersze „Ochłodzenie” (`+N%`) i „Przymrozek” (`N%`), linia „Parowanie (5–21 dni): N mm”.
- Nie odpytywać masowo Open-Meteo; jedno zapytanie kontrolne (2 punkty) dozwolone.
- Testy: `.venv/bin/pytest -q`, `node --test web/tests/*.test.js`.

## Review Focus

1. **`DailySeries` bez nowych serii** (stare fixture'y, historyczne dane bez zmiennej) — model działa jak przed planem (`et0` → 0, głęboka → płytka, brak `t2m_min` → `frost = 1`). Test w Task 2.
2. **Seria krótsza niż okno impulsu** (pierwsze dni `past_days`) — `pulse = 1.0`, bez `IndexError`. Test w Task 2.
3. **Przymrozek w dniu `i` i w dniu `i−7`** — granice: 0.2 i 1.0. Test w Task 2.
4. **Stary klient z nowym `pogoda.json` i nowy klient ze starym** — popup bez nowych wierszy, bez wyjątku na brakujących polach. Test w Task 4.
5. **`null` w nowych zmiennych godzinowych/dziennych** — `_fill_nearest` jak dla istniejących; zmienna całkiem pusta → seria `None` (zamiast przerywać cały przebieg). Test w Task 1.

---

### Task 1: Nowe zmienne w `forecast/weather.py`

**Files:**
- Modify: `forecast/weather.py`, `forecast/model.py` (`DailySeries`)
- Create: `tests/fixtures/openmeteo_two_points_v2.json` (kopia istniejącego fixture'a z `et0_fao_evapotranspiration`, `temperature_2m_min`, `soil_moisture_9_to_27cm`)
- Test: `tests/test_weather.py`

**Interfaces:**
- Produces:
  - `PARAMS["daily"] = "precipitation_sum,et0_fao_evapotranspiration,temperature_2m_min"`, `PARAMS["hourly"] = "soil_temperature_6cm,soil_moisture_3_to_9cm,soil_moisture_9_to_27cm"`.
  - `DailySeries` — nowe pola na końcu: `et0: list[float] | None = None`, `t2m_min: list[float] | None = None`, `soil_moisture_deep: list[float] | None = None`.
  - `daily_from_response` wypełnia je; zmienna nieobecna w odpowiedzi lub w całości `null` → `None` (nie `WeatherError`); `et0` z `null` → 0.0 dzień po dniu (jak opad); `t2m_min`, `soil_moisture_deep` → `_fill_nearest`.

- [ ] **Step 1: Testy**

```python
def test_v2_fixture_parses_new_series():   # et0[0], t2m_min[0], soil_moisture_deep[0] == wartości z fixture
def test_missing_new_variables_gives_none():  # stary fixture -> et0 is None, t2m_min is None, soil_moisture_deep is None
def test_all_null_new_variable_gives_none():  # soil_moisture_9_to_27cm same null -> None
def test_params_request_new_variables():   # "et0_fao_evapotranspiration" in PARAMS["daily"] itd.
```

- [ ] **Step 2: Uruchom** `.venv/bin/pytest tests/test_weather.py -q` — FAIL.
- [ ] **Step 3: Implementacja** wg Interfaces.
- [ ] **Step 4: Uruchom** `.venv/bin/pytest -q` — PASS. Zapytanie kontrolne: `.venv/bin/python -c "from forecast.weather import fetch_series; s=fetch_series([('a',50.3,18.7),('b',50.5,17.2)]); print({k:(v.et0[:2], v.t2m_min[:2], v.soil_moisture_deep[:2]) for k,v in s.items()})"` — oczekiwane: liczby, nie `None`.
- [ ] **Step 5: Commit** `feat(forecast): ET0, minimum temperatury i wilgotność 9–27 cm z Open-Meteo`

---

### Task 2: Nowe składowe w `forecast/model.py`

**Files:**
- Modify: `forecast/model.py`, `forecast/species.py`
- Test: `tests/test_model.py`, `tests/test_species.py`

**Interfaces:**
- Consumes: `DailySeries` (Task 1).
- Produces:
  - `water(s, i) -> float` — ważona suma opadu minus `ET_ALPHA ×` ważona suma `et0` w `RAIN_WINDOW` (wagi jak dziś); `et0 is None` → człon 0.
  - `soil_moisture_eff(s, i) -> float | None` — średnia z `MOISTURE_LOOKBACK` z `0.5·płytka + 0.5·głęboka` (bez głębokiej → płytka).
  - `pulse_factor(s, i) -> float`, `frost_factor(s, i, sp) -> float` wg spec §3.3–3.4.
  - `WeatherComponents(w, rain, temp, season, pulse, frost)`; `weather_multiplier` → `w = min(1.0, rain*temp*season*pulse*frost)`.
  - `limiting_factor` — kod `"frost"`; kolejność remisu z Global Constraints.
  - `WeatherValues` dostaje `et0_mm: float | None`, `soil_m_deep: float | None`, `t2m_min: float | None` (suma ET0 w `RAIN_WINDOW`, średnia głębokiej z `MOISTURE_LOOKBACK`, minimum `t2m_min` z dni `i-FROST_RECOVERY_DAYS..i`).
  - `Species.frost_min: float = DEFAULT_FROST_MIN`.

- [ ] **Step 1: Testy**

```python
def test_alpha_zero_reproduces_old_rain(monkeypatch):   # monkeypatch ET_ALPHA=0 -> rain_factor == wartości z istniejących przypadków testowych
def test_high_et0_lowers_rain():
def test_deep_moisture_lifts_penalty():                 # płytka 0.10, głęboka 0.30, próg 0.15 -> bez kary
def test_pulse_values():                                # spadek 0 -> 1.0; 1.5 °C -> 1.1; 3 -> 1.2; 6 -> 1.2; wzrost -> 1.0; i < 14 -> 1.0
def test_frost_recovery():                              # przymrozek w dniu i -> 0.2; i-3 -> 0.2+0.8*3/7; i-7 -> 1.0; frost_min z gatunku
def test_w_capped_at_one():                             # rain=temp=season=1, pulse 1.2 -> w == 1.0
def test_limiting_frost_and_tie_order():                # frost 0.2 i temp 0.2 -> "frost"; season 0.1 i frost 0.1 -> "season"
def test_series_without_new_fields_unchanged():         # DailySeries bez et0/t2m_min/deep -> pulse/frost liczone, frost == 1.0, rain jak ET_ALPHA=0
```

- [ ] **Step 2: Uruchom** `.venv/bin/pytest tests/test_model.py tests/test_species.py -q` — FAIL.
- [ ] **Step 3: Implementacja** wg Interfaces.
- [ ] **Step 4: Uruchom** `.venv/bin/pytest -q` — PASS.
- [ ] **Step 5: Commit** `feat(forecast): bilans wodny, wilgotność dwóch warstw, impuls ochłodzenia i przymrozek`

---

### Task 3: `pogoda.json`, schemat, dokumentacja, rozmiar partii

**Files:**
- Modify: `forecast/run.py` (`build_payload`), `schema/pogoda.schema.json`, `docs/data/api.md` (sekcja `pogoda.json`), `forecast/weather.py` (komentarz/`batch`)
- Test: `tests/test_run.py`

**Interfaces:**
- Consumes: `WeatherComponents`, `WeatherValues` (Task 2).
- Produces: `cells[cell][gatunek]` z `pulse` i `frost`; `wx[cell]` z `et0_mm` (1 miejsce), `soil_m_deep` (3 miejsca), `t2m_min` (1 miejsce) — tylko gdy wartości nie są `None` dla wszystkich 8 dni; schemat: `series_pulse` (`minimum: 1`, `maximum: 1.2`), nowe pola poza `required`, `lim` z `"frost"`.

- [ ] **Step 1: Testy**

```python
def test_payload_has_pulse_frost_and_wx_extras():   # build_payload na seriach z nowymi polami -> klucze obecne, waliduje się schematem
def test_payload_without_new_series_omits_wx_extras():  # serie bez et0 -> brak et0_mm w wx; waliduje się
def test_old_pogoda_fixture_still_validates():      # tests/fixtures/pogoda_v1.json przechodzi nowy schemat
```

- [ ] **Step 2: Uruchom** `.venv/bin/pytest tests/test_run.py -q` — FAIL.
- [ ] **Step 3: Implementacja**; rozmiar partii: trzecia zmienna godzinowa zwiększa wagę zapytania ~1,5× — ustawić domyślne `batch=30` w `fetch_series` i zaktualizować komentarz przy `RATE_LIMIT_WAIT_S` (nowe wyliczenie wagi).
- [ ] **Step 4: Uruchom** `.venv/bin/pytest -q` — PASS.
- [ ] **Step 5: Commit** `feat(forecast): nowe składowe i wartości w pogoda.json`

---

### Task 4: Popup

**Files:**
- Modify: `web/js/data.js` (`weatherFor`), `web/js/popup.js`
- Test: `web/tests/popup.test.js`, `web/tests/data.test.js`

**Interfaces:**
- Produces: `weatherFor` zwraca też `pulse`, `frost` (lub `null`) oraz w `wx` pola `et0_mm`, `soil_m_deep`, `t2m_min` (lub brak); `LIM_TEXT.frost`; w „Szczegółach modelu” wiersze „Ochłodzenie” (`+${round((pulse-1)*100)}%`) i „Przymrozek” (`pct(frost)`) tylko gdy pola są liczbami; `formatWx` zwraca `et0: "Parowanie (5–21 dni): N mm"` gdy jest `et0_mm`, a popup dodaje wtedy trzeci wiersz.

- [ ] **Step 1: Testy**

```js
test("LIM_TEXT ma przymrozek", ...)                       // LIM_TEXT.frost === "Ogranicza: niedawny przymrozek"
test("popup bez nowych pól nie ma wierszy Ochłodzenie/Przymrozek", ...)   // fixture pogoda_v1
test("popup z pulse i frost pokazuje wiersze", ...)      // pulse 1.1 -> "+10%", frost 0.6 -> "60%"
test("formatWx z et0_mm dodaje parowanie", ...)          // et0_mm 23.4 -> "Parowanie (5–21 dni): 23,4 mm"
```

- [ ] **Step 2: Uruchom** `node --test web/tests/popup.test.js web/tests/data.test.js` — FAIL.
- [ ] **Step 3: Implementacja** wg Interfaces.
- [ ] **Step 4: Uruchom** `node --test web/tests/*.test.js` — PASS.
- [ ] **Step 5: Commit** `feat(web): przymrozek, ochłodzenie i parowanie w popupie`

---

### Task 5: Strojenie `ET_ALPHA` raportem walidacji

Wymaga ukończonego planu H.

- [ ] **Step 1:** Dla `ET_ALPHA ∈ {0.0, 0.15, 0.3, 0.5}`: `.venv/bin/python -m pipeline.validate` (pogoda z cache po pierwszym przebiegu) i zapisać AUC pogody per gatunek. Historyczne serie potrzebują nowych zmiennych — `pipeline/meteo_hist.py` bierze `PARAMS` z `forecast.weather`, więc cache sprzed Task 1 trzeba odświeżyć (`--refresh` przy pierwszym przebiegu).
- [ ] **Step 2:** Ustawić `ET_ALPHA` na wartość z najwyższą średnią AUC po gatunkach z wynikiem (remis → mniejsza). Jeśli `pulse` lub `frost` obniżają AUC (porównanie z ich wyłączeniem: `PULSE_MAX = 0`, `FROST_FLOOR = 1`), wyłączyć je i opisać.
- [ ] **Step 3:** `.venv/bin/pytest -q` — PASS (testy używają monkeypatch dla stałych, nie zależą od wybranej wartości poza testem regresji `ET_ALPHA=0`).
- [ ] **Step 4: Commit** `chore(forecast): ET_ALPHA dobrane walidacją` z tabelą AUC w opisie.
