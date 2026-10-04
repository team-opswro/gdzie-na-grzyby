# M. Bilans wodny podłoża — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nowa składowa `moist` (wiadro wody podłoża, FAO-56) w mnożniku pogody, zastępująca `ET_ALPHA` i karę z wilgotności Open-Meteo; korekta wilgotności miejsca liczona z `moist`.

**Architecture:** `forecast/model.py` liczy wiadro na `DailySeries` (opad, ET0) i `moist`; `forecast/run.py` zapisuje `moist` oraz `wx.water`/`wx.dry_days`; klient (`data.js`, `map.js`, `popup.js`) używa `moist` z fallbackiem na `rain`; `pipeline/validate.py` używa `moist` w raporcie wilgotności miejsca.

**Tech Stack:** Python 3 (pytest), plain ES modules (node --test).

**Spec:** `docs/superpowers/specs/2026-10-04-m-bilans-wodny-design.md`

## Global Constraints

- Stałe w `forecast/model.py`: `BUCKET_MM = 25.0`, `BUCKET_KC = 0.8`, `MOIST_LOW = 0.1`, `MOIST_HIGH = 0.7`, `MOIST_FLOOR = 0.1`, `ET_ALPHA = 0.0`, `DRY_DAY_MM = 1.0`.
- Wiadro: `S_0 = C`, `S_j = min(C, max(0, S_{j−1} + P_j − KC·ET0_j))` dla `j = 0 … i−1`; `f = S/C`.
- Kod `lim` dla `moist`: `dry_soil`; kolejność remisu: season, frost, temp, moist, rain.
- Komentarze, teksty UI, commity — po polsku; conventional commits.
- `pogoda.json` zgodny wstecz: nowe pola opcjonalne w schemacie; `docs/data/api.md` zaktualizowane.

## Review Focus

- Seria bez `et0` (stary cache, brak zmiennej) → `moist` = 1,0, `water`/`dry_days` pominięte w `wx` — test w Task 1 i Task 2.
- Stary `pogoda.json` bez `moist` w nowym kliencie → korekta wet z `rain` (jak dziś) — test w Task 3.
- `moist` = `MOIST_FLOOR` (głęboka susza) i `wet` = 100 → `w_eff` > `w` (wilgotne miejsce ratuje wynik) — test w Task 1.
- Dzień `i` = 0 (początek serii) → `f` = 1, `dry_days` = 0 — test w Task 1.
- `dry_days` przy braku deszczu w całej historii → liczba dni historii (≤ 30), nie błąd — test w Task 1.

---

### Task 1: Wiadro i składowa `moist` w modelu

**Files:**
- Modify: `forecast/model.py`, `forecast/species.py`, `species.yaml` (usunąć `soil_moisture_min`)
- Test: `tests/test_model.py`, `tests/test_species.py`

**Interfaces:**
- Produces: `bucket_fraction(s: DailySeries, i: int) -> float | None` (None gdy `s.et0 is None`); `moist_factor(s, i) -> float`; `dry_days(s, i) -> int`; `WeatherComponents.moist: float` (pole po `rain`); `WeatherValues.water: float | None`, `WeatherValues.dry_days: int`; `limiting_factor` zwraca `dry_soil` dla `moist`.
- Usuwa: `MOISTURE_PENALTY`, `MOISTURE_SHALLOW_WEIGHT`, `soil_moisture_eff`, `Species.soil_moisture_min`, `DEFAULT_SOIL_MOISTURE_MIN`; `_rain_parts` → sam `rain_factor`.

- [ ] **Step 1: Testy (zastąpić stare testy kary/`ET_ALPHA` = 0.15)**

```python
def test_bucket_full_after_rain_and_drains_with_et0():
    s, i = series({1: 30.0}, et0=[2.5] * 37)
    assert bucket_fraction(s, i) == pytest.approx(1.0)
    s, i = series({}, et0=[2.5] * 37)  # 30 dni bez deszczu
    assert bucket_fraction(s, i) == 0.0

def test_bucket_start_and_no_et0():
    s, _ = series({}, et0=[2.5] * 37)
    assert bucket_fraction(s, 0) == 1.0 and dry_days(s, 0) == 0
    s, i = series({})
    assert bucket_fraction(s, i) is None and moist_factor(s, i) == 1.0

def test_moist_ramp_and_floor():  # f=0.4 -> 0.1+0.9*0.5 ; f<=0.1 -> MOIST_FLOOR ; f>=0.7 -> 1
    ...  # monkeypatch bucket_fraction na 0.4 / 0.05 / 0.8 -> 0.55 / 0.1 / 1.0

def test_dry_days():
    s, i = series({3: 5.0, 1: 0.5}, et0=[2.0] * 37)
    assert dry_days(s, i) == 3          # 0,5 mm < DRY_DAY_MM
    s, i = series({}, et0=[2.0] * 37)
    assert dry_days(s, i) == 30

def test_field_case_505_176():  # fikstura tests/fixtures/m_case_505_176.json, dzień 2026-10-04
    c = weather_multiplier(s, i, B)
    assert c.w <= 0.5 and c.moist == pytest.approx(0.44, abs=0.02)
    assert limiting_factor(c, s, i, B) == "dry_soil"

def test_wet_site_lifts_w_in_deep_drought():
    assert wet_adjust(0.1, MOIST_FLOOR, 100) > 0.1
```

Też: `test_limiting_factor_dry_vs_dry_soil` przepisać (niski impuls → `dry`; deszcz w oknie impulsu i 12 suchych dni ET0 3 mm → `dry_soil`); `ET_ALPHA == 0.0`; `test_species`: brak atrybutu `soil_moisture_min`.

- [ ] **Step 2:** `.venv/bin/pytest tests/test_model.py tests/test_species.py -q` → FAIL (brak nazw).
- [ ] **Step 3:** Implementacja wg spec §1–3; `weather_multiplier` mnoży `moist`; `weather_values` wypełnia `water` (`bucket_fraction`) i `dry_days`.
- [ ] **Step 4:** `.venv/bin/pytest -q` → wszystkie PASS (poprawić testy innych modułów odwołujące się do usuniętych nazw).
- [ ] **Step 5:** commit `feat(forecast): bilans wodny podłoża — składowa moist zamiast kary z wilgotności i ET_ALPHA`

### Task 2: `pogoda.json` — zapis, schemat, dokumentacja

**Files:** Modify `forecast/run.py`, `schema/pogoda.schema.json`, `docs/data/api.md`; Test `tests/test_run.py`

**Interfaces:** Consumes Task 1 (`WeatherComponents.moist`, `WeatherValues.water/dry_days`). Produces: `cells[c][sp].moist` (seria 0–1, zawsze), `wx[c].water` (0–1, 2 miejsca; tylko gdy wszystkie dni nie-None), `wx[c].dry_days` (int ≥ 0).

- [ ] **Step 1:** Testy: payload zawiera `moist` dla każdego gatunku, `wx.water` i `wx.dry_days` z `et0`; bez `et0` brak `water`; plik przechodzi `write_atomic` (schemat).
- [ ] **Step 2:** uruchomić → FAIL.
- [ ] **Step 3:** `build_payload`: dodać `"moist"` do listy składowych; `wx` jak wyżej. Schemat: `moist` (`series`), `water` (`series`), `dry_days` (tablica 8 liczb całkowitych ≥ 0). `api.md`: pola + nowe znaczenie `dry_soil` + zmiana `w_eff` na `moist` (fallback `rain`).
- [ ] **Step 4:** `.venv/bin/pytest -q` → PASS.
- [ ] **Step 5:** commit `feat(forecast): moist, zapas wody i dni bez deszczu w pogoda.json`

### Task 3: Klient — korekta wet z `moist`, popup, opis modelu

**Files:** Modify `web/js/data.js`, `web/js/map.js`, `web/js/popup.js`, `web/index.html`; Test `web/tests/data.test.js`, `web/tests/map.test.js`, `web/tests/popup.test.js`

**Interfaces:** `weatherFor(...)` zwraca dodatkowo `moist` (null gdy brak) i w `wx` pola `water`, `dry_days`; korekta `adjustW(w, moist ?? rain, wet, G)`. `formatWx(wx)` zwraca dodatkowo `water` = `"Zapas wody w podłożu: 35%"` + `" · bez deszczu od N dni"` dla N ≥ 3 (brak `wx.water` → brak klucza).

- [ ] **Step 1:** Testy: `weatherFor` z `moist` 0,5 i `rain` 1,0 koryguje wg `moist`; bez `moist` — wg `rain`; `map.js` wyrażenie używa `moist` z fallbackiem; `formatWx({..., water: 0.35, dry_days: 10})` → `"Zapas wody w podłożu: 35% · bez deszczu od 10 dni"`, `dry_days` 2 → bez dopisku; `LIM_TEXT.dry_soil === "Ogranicza: przesuszone podłoże"`; „Szczegóły modelu” zawierają wiersz „Wilgotność podłoża”.
- [ ] **Step 2:** `node --test web/tests/data.test.js web/tests/map.test.js web/tests/popup.test.js` → FAIL.
- [ ] **Step 3:** Implementacja; `index.html`: opis pogody wg spec §6.
- [ ] **Step 4:** `node --test web/tests/*.test.js` → PASS.
- [ ] **Step 5:** commit `feat(web): wilgotność podłoża w popupie i korekta wilgotności miejsca z moist`

### Task 4: Walidacja — `wet_eval` z `moist`, bezpiecznik GBIF

**Files:** Modify `pipeline/validate.py`, `scripts/check_wet_case.py` (W/RAIN → wartości z fikstury); Test `tests/test_validate.py`

- [ ] **Step 1:** Test: `wet_eval` woła `adjust(c.w, c.moist, wet)`; dzień suchy = `c.moist < DRY_MOIST` (0,8).
- [ ] **Step 2–4:** implementacja, `.venv/bin/pytest -q` PASS.
- [ ] **Step 5:** `.venv/bin/python -m pipeline.validate --species borowik,podgrzybek --wet --out pipeline/data/walidacja-m --compare pipeline/data/walidacja-m-baza/walidacja.json`. Kryterium: AUC `w` borowik ≥ 0,559, podgrzybek ≥ 0,584. Wynik (i ewentualną decyzję) dopisać do spec jako „Decyzje po walidacji”.
- [ ] **Step 6:** commit `feat(pipeline): walidacja wilgotności miejsca z moist; wyniki spec M`
