# H. Walidacja modelu na obserwacjach — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `python -m pipeline.validate` liczy z obserwacji GBIF AUC/lift siedliska `h` i AUC pogody `w` (oraz ich składowych) per gatunek i zapisuje raport `walidacja.json` + `walidacja.md`.

**Architecture:** `pipeline/gbif.py` pobiera i cache'uje obserwacje (gatunki + tło „wszystkie grzyby”); `pipeline/meteo_hist.py` pobiera i cache'uje historyczne serie Open-Meteo tym samym parserem co prognoza; `pipeline/validate.py` łączy obserwacje z wydzieleniami, liczy metryki przez rejestr czynników z `pipeline/habitat.py` i `forecast/model.py`, renderuje raport. Wszystko offline, nic nie trafia do `pipeline/data/out/` ani do bucketu.

**Tech Stack:** Python 3, geopandas/shapely, requests, pytest + responses.

**Spec:** `docs/superpowers/specs/2026-10-03-h-walidacja-obserwacje-design.md`

## Global Constraints

- Komentarze, komunikaty, raport i commity po polsku; commity `feat(pipeline): …` / `refactor(pipeline): …` / `test(pipeline): …`.
- Wynik wyłącznie w `pipeline/data/walidacja/` (już w `.gitignore`); **nigdy** w `pipeline/data/out/` (publish wysyła cały katalog).
- Cache: `pipeline/data/raw/gbif/<klucz>/<offset>.json`, `pipeline/data/raw/meteo/<cell>_<rok>.json`; ponowny przebieg bez HTTP, chyba że `--refresh`.
- GBIF: `species/match?name=<latin>&kingdom=Fungi`, akceptacja `matchType ∈ {EXACT, FUZZY}` i `rank == SPECIES`; `occurrence/search` z `hasCoordinate=true`, `hasGeospatialIssue=false`, `basisOfRecord=HUMAN_OBSERVATION`, `occurrenceStatus=PRESENT`, `year=2000,<bieżący>`, `limit=300`, twardy limit 100 000 rekordów; tło: `kingdomKey=5`. HTTP: timeout 30 s, 3 próby z backoffem, pauza 0,2 s między stronami.
- Filtr rekordu: `coordinateUncertaintyInMeters` ≤ 100 (brak → odrzut), data z dokładnością do dnia (brak `day` lub `/` w `eventDate` → odrzut), punkt w `obszar.geojson`.
- Tło siedliska: wydzielenia z obserwacją dowolnego grzyba bez obecności gatunku; próba ≤ 20 × obecności; `MIN_PRESENCES = 30`; lift przy `h ≥ 0.6`.
- Pogoda: obserwacje od `2022-01-01`; seria na (komórka, rok) od `<rok>-04-10` do `min(<rok>-11-30, dziś − 1)`; tło 5 losowych dni na obecność z okna sezonu gatunku ± 14 dni tego roku, bez dni z obserwacją gatunku w tej komórce; zapytania sekwencyjne z pauzą 1 s, 429 jak w `forecast/weather.py`.
- AUC: Mann–Whitney, remis = ½; deterministyczne losowanie (`seed=0`).
- Testy bez sieci (`responses`). Komendy: `.venv/bin/pytest -q`.

## Review Focus

1. **`eventDate` w różnych formatach** (`2023-09-14`, `2023-09-14T10:00:00+02:00`, zakres `2023-09-01/2023-09-30`) — pierwsze dwa dają dzień 2023-09-14, zakres jest odrzucany. Test w Task 2.
2. **Obserwacja na granicy dwóch wydzieleń / duplikat po sjoin** — liczona raz (pierwsze trafienie per `gbif_id`). Test w Task 4.
3. **Brak tła albo brak obecności dla gatunku** — `auc` zwraca `None`, raport pokazuje „—”, bez `ZeroDivisionError`. Test w Task 4.
4. **`--species` z podzbiorem** — wyniki pozostałych gatunków są identyczne jak w pełnym przebiegu (RNG seedowany per gatunek, nie globalnie). Test w Task 4.
5. **Data obserwacji poza serią pogodową** (rok bieżący po `dziś − 1`, przed 2022, poza `04-10..11-30`) — pominięta i policzona w `n_skipped`, bez `IndexError`. Test w Task 5.

---

### Task 1: Rejestr czynników siedliska i wspólny `stand_from_row`

**Files:**
- Modify: `pipeline/habitat.py`
- Modify: `pipeline/build_tiles.py:38-50`
- Test: `tests/test_habitat.py`, `tests/test_build_tiles.py`

**Interfaces:**
- Produces:
  - `stand_from_row(sp_main, sp_admix, age, hab, partners) -> Stand` — normalizuje `age`/wiek partnerów (`NaN`/`pd.NA` → `None`, inaczej `int`) i krotki, jak dziś robi `build_tiles`; `build_tiles` używa go zamiast lokalnego `_age` i budowy klucza (klucz cache = zwrócony `Stand`, który jest frozen/hashowalny).
  - `habitat_components(st: Stand, sp: Species) -> dict[str, float]` — klucze `"partner"`, `"habitat"`, `"age"` (`age` = `age_factor(st.age, sp)`; diagnostyczny).
  - `habitat_score(st, sp, neutral: frozenset[str] = frozenset()) -> float` — `"habitat"` w `neutral` → `habitat_factor` = 1.0; `"age"` w `neutral` → w `partner_score` każdy `age_factor` = 1.0 (gatunek panujący-partner → 1.0, domieszka → sama waga udziału); `"partner"` w `neutral` → ocena partnera = 1.0.
  - `partner_score(st, sp, use_age: bool = True) -> float`.
  - `HABITAT_FACTORS: tuple[str, ...] = ("partner", "habitat", "age")` — lista nazw dla raportu; spec F/I dopisują tu swoje.

- [ ] **Step 1: Testy**

```python
def test_components_keys_and_values():
    st = Stand("SO", (), 25, "BMW")
    c = habitat_components(st, S["borowik"])
    assert set(c) == set(HABITAT_FACTORS) == {"partner", "habitat", "age"}
    assert c["habitat"] == pytest.approx(0.6)          # BMW = adjacent dla borowika
    assert c["age"] == 0.0                              # 25 < age_min 30

def test_score_unchanged_without_neutral():
    st = Stand("SO", ("BRZ",), 60, "BSW", (("BRZ", "2", 40),))
    for sp in S.values():
        assert habitat_score(st, sp) == partner_score(st, sp) * habitat_factor(st.hab, sp)

def test_neutral_habitat_and_age():
    st = Stand("SO", (), 25, "BMW")
    assert habitat_score(st, S["borowik"], neutral=frozenset({"habitat"})) == 0.0
    assert habitat_score(st, S["borowik"], neutral=frozenset({"age"})) == pytest.approx(0.6)
    assert habitat_score(st, S["borowik"], neutral=frozenset({"age", "habitat"})) == 1.0

def test_neutral_age_admixture_uses_share_weight():
    st = Stand("BRZ", ("SO",), 60, "BSW", (("SO", "2", 10),))
    assert habitat_score(st, S["borowik"], neutral=frozenset({"age"})) == pytest.approx(0.7)

def test_stand_from_row_normalizes_nan_ages():
    st = stand_from_row("SO", ["BRZ"], float("nan"), "BSW", [("BRZ", "2", pd.NA)])
    assert st == Stand("SO", ("BRZ",), None, "BSW", (("BRZ", "2", None),))
```

W `tests/test_build_tiles.py` istniejące testy `compute_features` muszą przechodzić bez zmian (regresja refaktoru).

- [ ] **Step 2: Uruchom** `.venv/bin/pytest tests/test_habitat.py -q` — oczekiwane: FAIL (`ImportError: habitat_components`).
- [ ] **Step 3: Implementacja** w `pipeline/habitat.py` wg Interfaces; `build_tiles.compute_features` buduje `Stand` przez `stand_from_row` i używa go jako klucza cache.
- [ ] **Step 4: Uruchom** `.venv/bin/pytest -q` — oczekiwane: wszystko PASS.
- [ ] **Step 5: Commit** `refactor(pipeline): rejestr czynników siedliska i wspólne budowanie Stand`

---

### Task 2: Pobieranie obserwacji z GBIF (`pipeline/gbif.py`)

**Files:**
- Create: `pipeline/gbif.py`
- Create: `tests/test_gbif.py`, `tests/fixtures/gbif_match.json`, `tests/fixtures/gbif_page0.json`, `tests/fixtures/gbif_page1.json`

**Interfaces:**
- Produces:
  - `GBIF_API = "https://api.gbif.org/v1"`, `PAGE = 300`, `MAX_RECORDS = 100_000`, `MAX_UNCERTAINTY_M = 100`
  - `match_taxon(latin: str, *, session=None) -> int | None`
  - `area_wkt(area) -> str` — prostokąt otaczający geometrię, wierzchołki przeciwnie do ruchu wskazówek (`POLYGON((minx miny, maxx miny, maxx maxy, minx maxy, minx miny))`), współrzędne `lon lat`.
  - `fetch_records(query: dict, cache_dir: Path, *, refresh=False, session=None, sleep=time.sleep) -> list[dict]` — strona `offset` czytana z `cache_dir/<offset>.json`, jeśli istnieje i nie `refresh`; inaczej GET + zapis; kończy na `endOfRecords` albo `MAX_RECORDS`; między pobranymi z sieci stronami `sleep(0.2)`; błąd po 3 próbach (backoff `sleep(2**n)`) → `GbifError`.
  - `base_query(area, year_to: int) -> dict` — parametry wspólne z Global Constraints + `geometry=area_wkt(area)`, `limit=PAGE`.
  - `parse_day(rec: dict) -> date | None` — `None`, gdy brak `year`/`month`/`day` lub `/` w `eventDate`.
  - `clean(records: list[dict], area, label: str) -> pd.DataFrame` — kolumny `species` (= `label`), `gbif_id` (`rec["key"]`), `lat`, `lon`, `date`; filtry z Global Constraints; duplikaty `gbif_id` usunięte.
  - `load_observations(latin_by_key: dict[str, str], area, cache_root: Path, *, refresh=False, session=None, sleep=time.sleep, year_to: int) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]` — (obecności wszystkich gatunków, tło z `label="*"` z zapytania `kingdomKey=5` w `cache_root/"fungi"`, lista ostrzeżeń dla niedopasowanych taksonów). Cache gatunku: `cache_root/<key>`.

- [ ] **Step 1: Testy** (`responses`, fixture strony 0 z `endOfRecords: false`, strona 1 z `true`)

```python
def test_match_taxon_accepts_species_exact_and_rejects_genus(): ...
    # EXACT/SPECIES -> usageKey; rank GENUS -> None; matchType NONE -> None
def test_area_wkt_counter_clockwise():
    assert area_wkt(box(17.0, 49.5, 19.0, 51.0)) == \
        "POLYGON((17.0 49.5, 19.0 49.5, 19.0 51.0, 17.0 51.0, 17.0 49.5))"
def test_fetch_paginates_and_caches(tmp_path):
    # 2 żądania (offset 0 i 300); drugi przebieg: 0 żądań (responses.calls == 2), ten sam wynik
def test_fetch_refresh_refetches(tmp_path): ...       # refresh=True -> znowu 2 żądania
def test_fetch_stops_at_max_records(tmp_path, monkeypatch): ...  # MAX_RECORDS=300 -> 1 żądanie
def test_parse_day_formats():
    assert parse_day({"year": 2023, "month": 9, "day": 14, "eventDate": "2023-09-14"}) == date(2023, 9, 14)
    assert parse_day({"year": 2023, "month": 9, "day": 14, "eventDate": "2023-09-14T10:00:00+02:00"}) == date(2023, 9, 14)
    assert parse_day({"year": 2023, "month": 9, "eventDate": "2023-09-01/2023-09-30"}) is None
    assert parse_day({"year": 2023, "month": 9, "day": 1, "eventDate": "2023-09-01/2023-09-30"}) is None
def test_clean_filters_uncertainty_area_and_duplicates():
    # niepewność 50 -> zostaje, 150 -> odrzut, brak -> odrzut; punkt poza area -> odrzut; ten sam key 2x -> 1 wiersz
def test_load_observations_warns_on_unmatched_taxon(tmp_path): ...
```

- [ ] **Step 2: Uruchom** `.venv/bin/pytest tests/test_gbif.py -q` — FAIL (brak modułu).
- [ ] **Step 3: Implementacja** `pipeline/gbif.py` wg Interfaces (requests; `session or requests` jak w `forecast/weather.py`).
- [ ] **Step 4: Uruchom** `.venv/bin/pytest tests/test_gbif.py -q` — PASS.
- [ ] **Step 5: Commit** `feat(pipeline): pobieranie obserwacji grzybów z GBIF z cache`

---

### Task 3: Historyczne serie pogodowe (`pipeline/meteo_hist.py`)

**Files:**
- Modify: `forecast/weather.py` (`_request` dostaje parametr `url: str = API_URL`)
- Create: `pipeline/meteo_hist.py`
- Test: `tests/test_meteo_hist.py` (fixture: istniejące `tests/fixtures/openmeteo_two_points.json`, element `[0]`)

**Interfaces:**
- Consumes: `forecast.weather.PARAMS`, `forecast.weather._request(params, retries, sleep, session, url=...)`, `forecast.weather.daily_from_response`, `pipeline.grid.cell_center`.
- Produces:
  - `HIST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"`, `HIST_START = date(2022, 1, 1)`, `SEASON_FROM = (4, 10)`, `SEASON_TO = (11, 30)`
  - `year_range(year: int, today: date) -> tuple[date, date] | None` — `None`, gdy `year < 2022` albo początek ≥ `today`.
  - `hist_params(cell: str, start: date, end: date) -> dict` — `daily`/`hourly`/`timezone` z `PARAMS` (bez `past_days`, `forecast_days`), `latitude`/`longitude` z `cell_center`, `start_date`/`end_date` ISO.
  - `fetch_year(cell: str, year: int, cache_dir: Path, *, today: date, refresh=False, session=None, sleep=time.sleep) -> DailySeries | None` — cache `cache_dir/f"{cell}_{year}.json"` (surowa odpowiedź); po pobraniu z sieci `sleep(1)`.

- [ ] **Step 1: Testy**

```python
def test_year_range_bounds():
    assert year_range(2021, date(2026, 10, 3)) is None
    assert year_range(2023, date(2026, 10, 3)) == (date(2023, 4, 10), date(2023, 11, 30))
    assert year_range(2026, date(2026, 10, 3)) == (date(2026, 4, 10), date(2026, 10, 2))
    assert year_range(2026, date(2026, 4, 10)) is None
def test_hist_params_has_no_past_or_forecast_days():
    p = hist_params("493_189", date(2023, 4, 10), date(2023, 11, 30))
    assert "past_days" not in p and "forecast_days" not in p
    assert (p["latitude"], p["longitude"]) == (49.35, 18.95)
    assert p["hourly"] == PARAMS["hourly"] and p["start_date"] == "2023-04-10"
def test_fetch_year_caches(tmp_path): ...   # 1 żądanie na HIST_URL, drugi przebieg 0 żądań, DailySeries z fixture
def test_fetch_year_before_2022_no_request(tmp_path): ...  # None, 0 żądań
```

Istniejące `tests/test_weather.py` muszą przechodzić bez zmian.

- [ ] **Step 2: Uruchom** `.venv/bin/pytest tests/test_meteo_hist.py -q` — FAIL.
- [ ] **Step 3: Implementacja** wg Interfaces.
- [ ] **Step 4: Uruchom** `.venv/bin/pytest tests/test_meteo_hist.py tests/test_weather.py -q` — PASS.
- [ ] **Step 5: Commit** `feat(pipeline): historyczne serie Open-Meteo do walidacji`

---

### Task 4: Metryki i walidacja siedliska (`pipeline/validate.py`, część 1)

**Files:**
- Create: `pipeline/validate.py`
- Create: `tests/test_validate.py`

**Interfaces:**
- Consumes: `habitat_score(st, sp, neutral)`, `habitat_components`, `HABITAT_FACTORS`, `stand_from_row` (Task 1); DataFrame obserwacji z Task 2 (`species, gbif_id, lat, lon, date`).
- Produces:
  - `MIN_PRESENCES = 30`, `BG_RATIO = 20`, `LIFT_H = 0.6`, `SEED = 0`
  - `auc(pos: Sequence[float], neg: Sequence[float]) -> float | None` — `None`, gdy któraś lista pusta.
  - `rng_for(key: str) -> random.Random` — `random.Random(f"{SEED}:{key}")`.
  - `join_stands(obs: pd.DataFrame, stands: gpd.GeoDataFrame) -> tuple[pd.DataFrame, int]` — `obs` z kolumną `stand` (indeks wiersza `stands`), jedno trafienie na `gbif_id` (pierwsze po indeksie stands); drugi element = liczba obserwacji poza wydzieleniami.
  - `habitat_eval(key: str, sp: Species, stands: gpd.GeoDataFrame, presence: set[int], background: set[int]) -> dict` — tło = `background − presence`, próba `rng_for(key).sample(sorted(tło), BG_RATIO * len(presence))` gdy większe; zwraca `{"n_presence", "n_background", "status": "ok" | "za mało danych", "habitat": {"auc", "lift60", "factors": {<name>: {"auc", "ablation_auc"}}}}` (`habitat` = `None` przy „za mało danych”, czyli `len(presence) < MIN_PRESENCES`). `lift60` = (obecności z `h ≥ LIFT_H` / wszystkie z `h ≥ LIFT_H`) ÷ (obecności / cała próba); `None`, gdy brak wydzieleń z `h ≥ LIFT_H`.

- [ ] **Step 1: Testy**

```python
def test_auc_known_cases():
    assert auc([3, 4], [1, 2]) == 1.0
    assert auc([1, 2], [3, 4]) == 0.0
    assert auc([1, 1], [1, 1]) == 0.5
    assert auc([], [1]) is None and auc([1], []) is None
def test_join_counts_outside_and_dedupes_overlap():
    # dwa nakładające się kwadraty + punkt w części wspólnej + punkt poza -> 1 wiersz, outside == 1
def test_too_few_presences():
    r = habitat_eval("borowik", S["borowik"], stands, presence=set(range(29)), background=set(range(29, 200)))
    assert r["status"] == "za mało danych" and r["habitat"] is None
def test_perfect_separation_auc_one():
    # 30 obecności: Stand("SO", (), 80, "BSW"); 100 tła: Stand("OL", (), 60, "OL") -> auc == 1.0, lift60 > 1
def test_background_sample_capped_and_deterministic():
    # 30 obecności, 1000 tła -> n_background == 600; dwa wywołania -> identyczny wynik
def test_species_subset_independent():
    # habitat_eval dla "kurka" daje to samo niezależnie od tego, czy wcześniej wołano "borowik"
def test_empty_background_gives_none_auc():
    # 30 obecności, tło == obecności -> habitat["auc"] is None, bez wyjątku
def test_factor_ablation_keys():
    # r["habitat"]["factors"] ma klucze == set(HABITAT_FACTORS), każdy z "auc" i "ablation_auc"
```

`stands` w testach: mały `GeoDataFrame` z kolumnami jak `load_stands` (`sp_main, sp_admix, partners, age, hab`) i kwadratami jako geometrią; helper w pliku testu.

- [ ] **Step 2: Uruchom** `.venv/bin/pytest tests/test_validate.py -q` — FAIL.
- [ ] **Step 3: Implementacja** wg Interfaces (`geopandas.sjoin(..., predicate="within")`, `drop_duplicates("gbif_id")`).
- [ ] **Step 4: Uruchom** `.venv/bin/pytest tests/test_validate.py -q` — PASS.
- [ ] **Step 5: Commit** `feat(pipeline): walidacja siedliska na obserwacjach (AUC, lift, ablacja)`

---

### Task 5: Walidacja pogody (`pipeline/validate.py`, część 2)

**Files:**
- Modify: `pipeline/validate.py`
- Test: `tests/test_validate.py`

**Interfaces:**
- Consumes: `forecast.model.weather_multiplier`, `WeatherComponents`, `DailySeries`; `pipeline.grid.cell_id`; `auc`, `rng_for` (Task 4).
- Produces:
  - `WX_BG_PER_PRESENCE = 5`, `SEASON_MARGIN_DAYS = 14`
  - `weather_eval(key: str, sp: Species, obs: pd.DataFrame, series: Callable[[str, int], DailySeries | None]) -> dict` — `obs` = obserwacje gatunku (`lat, lon, date`); obecność = unikalne (`cell_id(lat, lon)`, `date`) z `date ≥ HIST_START`; `series(cell, year)` zwraca serię albo `None`. Indeks dnia w serii przez `dates.index`; dzień spoza serii → pominięty. Tło: dla każdej obecności `rng_for(key + ":wx")` losuje bez zwracania do 5 dni z dni serii w [start sezonu − 14, koniec sezonu + 14] tego roku, minus dni z obecnością gatunku w tej komórce. Zwraca `{"n", "n_skipped", "auc", "components": {<pole WeatherComponents poza w>: auc}}`; `n < MIN_PRESENCES` → `{"n", "n_skipped", "status": "za mało danych"}`.

- [ ] **Step 1: Testy** (syntetyczne `DailySeries` 2023-04-10..2023-11-30; `series` jako słownik w lambdzie)

```python
def test_weather_auc_one_when_presence_days_wet():
    # opad tylko w oknie 5–21 dni przed dniami obecności -> auc == 1.0, components["season"] obecne
def test_weather_skips_out_of_range_dates():
    # obserwacje 2021-09-01 i 2023-12-15 -> n_skipped == 2, bez wyjątku
def test_weather_series_none_skipped():
    # series zwraca None dla komórki -> obserwacje tej komórki w n_skipped
def test_weather_background_excludes_presence_days_and_is_deterministic(): ...
def test_weather_too_few():
    # 10 obecności -> status "za mało danych"
```

- [ ] **Step 2: Uruchom** `.venv/bin/pytest tests/test_validate.py -q` — FAIL dla nowych testów.
- [ ] **Step 3: Implementacja** wg Interfaces; składowe przez `dataclasses.fields(WeatherComponents)` z pominięciem `w`.
- [ ] **Step 4: Uruchom** `.venv/bin/pytest tests/test_validate.py -q` — PASS.
- [ ] **Step 5: Commit** `feat(pipeline): walidacja mnożnika pogodowego na obserwacjach`

---

### Task 6: Raport i CLI (`pipeline/validate.py`, część 3)

**Files:**
- Modify: `pipeline/validate.py`
- Test: `tests/test_validate.py`

**Interfaces:**
- Consumes: Task 2 `load_observations`, Task 3 `fetch_year`, Task 4 `join_stands`/`habitat_eval`, Task 5 `weather_eval`; `pipeline.ingest.load_stands`, `DEFAULT_DB`, `DEFAULT_PARQUET`, `DATA_DIR`; `forecast.species.load_species`; `content/gatunki.yaml` (`species.<key>.latin`).
- Produces:
  - `DEFAULT_OUT = DATA_DIR / "walidacja"`, `DEFAULT_AREA = DATA_DIR / "obszar.geojson"`, `DEFAULT_CACHE = DATA_DIR / "raw"`
  - `build_report(per_species: dict[str, dict], *, build: str | None, generated_at: str, outside: int, warnings: list[str]) -> dict` — kształt wg spec §6: `{"generated_at", "build", "outside", "warnings", "species": {<key>: {"n_presence", "n_background", "status", "habitat", "weather"}}}`.
  - `render_md(report: dict, baseline: dict | None = None) -> str` — tabela siedliska (gatunek, n, AUC, lift60, a przy `baseline` kolumna „Δ AUC”), tabela czynników (AUC, AUC po ablacji), tabela pogody (n, AUC, AUC składowych); `None` → „—”; gatunek „za mało danych” → wiersz `za mało danych (n=…)`; gatunek nieobecny w `baseline` → Δ „—”.
  - `main(argv=None) -> int` — opcje: `--species` (lista po przecinku; domyślnie wszystkie z `species.yaml`), `--refresh`, `--no-weather`, `--compare PATH`, `--out` (`DEFAULT_OUT`), `--db`, `--parquet`, `--area`, `--cache`. Zapisuje `walidacja.json` (`indent=1`, `ensure_ascii=False`, `sort_keys=True`) i `walidacja.md`; `build` z `pipeline/data/out/build.json` (pole `build`), jeśli plik istnieje. `generated_at` w JSON-ie i `.md` — jedyna rzecz różniąca dwa przebiegi.
  - `if __name__ == "__main__": raise SystemExit(main())`

- [ ] **Step 1: Testy**

```python
def test_render_md_with_baseline_delta():
    # baseline auc 0.60, nowy 0.65 -> w .md "+0.05"; gatunek bez baseline -> "—"
def test_render_md_too_few_and_none():
    # status "za mało danych" n=12 -> "za mało danych (n=12)"; lift60 None -> "—"
def test_main_end_to_end_offline(tmp_path, monkeypatch):
    # monkeypatch: load_stands -> mały GeoDataFrame, load_observations -> gotowe DataFrame'y,
    # fetch_year -> syntetyczna seria; main(["--out", str(tmp_path), "--species", "borowik"]) == 0;
    # tmp_path/"walidacja.json" i "walidacja.md" istnieją; json["species"].keys() == {"borowik"}
def test_main_deterministic(tmp_path, monkeypatch):
    # dwa przebiegi -> JSON identyczny po usunięciu "generated_at"
def test_main_no_weather(tmp_path, monkeypatch):
    # --no-weather -> fetch_year nie wołane, species[k]["weather"] is None
def test_default_out_not_in_publish_dir():
    assert DEFAULT_OUT.name == "walidacja" and "out" not in DEFAULT_OUT.parts[-2:]
```

- [ ] **Step 2: Uruchom** `.venv/bin/pytest tests/test_validate.py -q` — FAIL dla nowych testów.
- [ ] **Step 3: Implementacja** wg Interfaces; postęp na stderr (`print(..., file=sys.stderr)`): pobieranie GBIF per gatunek, liczba komórek×lat dla pogody.
- [ ] **Step 4: Uruchom** `.venv/bin/pytest -q` — wszystko PASS.
- [ ] **Step 5: Przebieg na prawdziwych danych** `.venv/bin/python -m pipeline.validate` (wymaga sieci i `pipeline/data/bdl.duckdb`, `stands.parquet`, `obszar.geojson`) — oczekiwane: `pipeline/data/walidacja/walidacja.md` z wierszem dla każdego z 6 gatunków; drugi przebieg bez żądań HTTP (log nie pokazuje pobierania). Skopiować `walidacja.json` → `pipeline/data/walidacja/walidacja-baza.json` (linia bazowa dla F/G/I). Liczby obecności per gatunek wpisać do opisu commita.
- [ ] **Step 6: Commit** `feat(pipeline): raport walidacji i CLI pipeline.validate`
