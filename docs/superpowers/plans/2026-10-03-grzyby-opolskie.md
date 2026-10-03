# Grzyby Opolskie Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Statyczna strona z mapą szans na 6 gatunków grzybów w wydzieleniach leśnych woj. opolskiego, z prognozą na 7 dni i rankingiem top 10 w okolicy, wdrożona na Coolify.

**Architecture:** Pipeline w Pythonie (lokalnie, raz na sezon) liczy ocenę siedliska `h` per wydzielenie i gatunek z danych BDL i generuje `lasy.pmtiles` + `centroidy.json` + `grid.json`. Kontener `forecast` 2×/dzień pobiera Open-Meteo dla ~100 komórek siatki 0,1° i zapisuje `pogoda.json` z mnożnikiem `w`. Frontend (MapLibre, bez frameworka) liczy `round(100 × h × w)` w przeglądarce.

**Tech Stack:** Python 3.12 (pyyaml, requests, jsonschema; pipeline: geopandas, shapely, pyogrio), pytest + responses, tippecanoe ≥ 2.17, JS (moduły ES) + maplibre-gl 4.x + pmtiles 3.x, Node ≥ 20 (`node:test`, tylko testy), nginx:alpine, supercronic, Docker Compose na Coolify.

**Spec:** `docs/superpowers/specs/2026-10-03-grzyby-opolskie-design.md`

## Global Constraints

- Klucze gatunków (dokładnie, w tej kolejności): `borowik`, `podgrzybek`, `kurka`, `kozlarz`, `maslak`, `rydz`.
- Parametry gatunków tylko w `species.yaml`; żadnych liczb gatunkowych w kodzie.
- Wynik: `score = round(100 × h × w)`, 0–100. `h` w kafelkach jako int 0–100 (`h_<klucz>`), więc w JS: `round(h_int × w)`.
- Siatka: 0,1°, `cell_id = f"{lat_idx}_{lon_idx}"`, `lat_idx = floor(round(lat*10, 6))`.
- Open-Meteo: `daily=precipitation_sum`, `hourly=soil_temperature_6cm,soil_moisture_3_to_9cm`, `past_days=30`, `forecast_days=7`, `timezone=Europe/Warsaw`.
- Prognoza nieaktualna: `generated_at` starszy niż 36 h.
- Ranking: promień 20 km, top 10; `centroidy.json` tylko gdy `max(h_*) ≥ 40`.
- Kafelki: warstwa `lasy`, zoom 8–14.
- Cron `forecast`: 05:00 i 14:00, `TZ=Europe/Warsaw`; jednorazowy przebieg przy starcie.
- Frontend: brak frameworka i kroku budowania; biblioteki lokalnie w `web/vendor/`.
- Ścieżki serwowane: `data/lasy.pmtiles`, `data/centroidy.json`, `data/live/pogoda.json`.
- Teksty UI po polsku.

## Review Focus

1. **Komórka wydzielenia nieobecna w `pogoda.json`** (np. siatka przebudowana, a forecast jeszcze nie) → polygon szary „brak danych”, ranking go pomija, nic się nie wysypuje. Test: Task 9 `weatherFor` zwraca `null`, `topN` pomija.
2. **Wartości `null` w godzinowych seriach Open-Meteo** (brakujące godziny/dni) → średnia z dostępnych; dzień bez danych: opad 0, temperatura/wilgotność z najbliższego dnia. Test: Task 4.
3. **`pogoda.json` zaczyna się przed dzisiejszą datą** (otwarcie strony o 01:00 przed przebiegiem 05:00, albo plik stary) → „dziś” w UI to bieżąca data, nie `days[0]`; dni z przeszłości niedostępne. Test: Task 9 `availableDays`.
4. **Kody gatunków drzew w BDL z wariantami** (`"DB.S"`, `" so "`, `"ŚW"`) → dopasowanie do partnerów po normalizacji. Test: Task 6 `normalize_species_code`.
5. **Wielokąt typu MultiPolygon / w kształcie litery C, którego centroid leży poza nim lub w innej komórce** → `cell` i współrzędne rankingu z `representative_point()`, nie z `centroid`. Test: Task 8.

---

### Task 1: Rozpoznanie danych BDL (bramka ryzyka)

Zadanie badawcze; bez kodu produkcyjnego. **Jeśli dane BDL są niedostępne, licencja zabrania użycia albo brak gatunku panującego lub wieku — STOP i decyzja użytkownika** (spec §9: awaryjnie OSM).

**Files:**
- Create: `docs/data/bdl.md`
- Create: `pipeline/bdl_fields.yaml`
- Create: `pipeline/data/opolskie.geojson` (granica województwa, EPSG:4326)

**Interfaces:**
- Produces: `pipeline/bdl_fields.yaml` w formacie:
  ```yaml
  source: "<URL lub opis pobrania>"
  layer: "<nazwa warstwy/pliku z wydzieleniami>"
  join: null            # albo opis złączenia z tabelą gatunków, jeśli atrybuty są osobno
  fields: {id: <kol>, sp_main: <kol>, sp_admix: <kol|null>, age: <kol>, hab: <kol|null>}
  forest_filter: {column: <kol>, values: [<wartości oznaczające drzewostan>]}
  districts: [<nazwy nadleśnictw obejmujących Opolskie>]
  ```

- [ ] **Step 1:** Na bdl.lasy.gov.pl ustal, skąd i na jakich warunkach można pobrać wydzielenia per nadleśnictwo (paczki danych, WFS, wniosek). Zapisz w `docs/data/bdl.md`: URL, licencję/warunki, format.
- [ ] **Step 2:** Ustal listę nadleśnictw, których zasięg przecina woj. opolskie (RDLP Katowice i Wrocław); zapisz w `districts`.
- [ ] **Step 3:** Pobierz dane jednego nadleśnictwa (np. Opole) do `pipeline/data/raw/` (katalog w `.gitignore`). Wypisz kolumny i 5 przykładowych rekordów (`python -c "import geopandas as g; d=g.read_file(...); print(d.dtypes); print(d.head())"`). Zapisz mapowanie w `pipeline/bdl_fields.yaml` i przykładowe wartości (kody gatunków, kody typów siedliskowych) w `docs/data/bdl.md`.
- [ ] **Step 4:** Pobierz granicę województwa (PRG lub OSM relacja „województwo opolskie”), uprość do ~100 m, zapisz `pipeline/data/opolskie.geojson`.
- [ ] **Step 5:** Pokaż użytkownikowi `docs/data/bdl.md`; przy problemach z §Task 1 — STOP.
- [ ] **Step 6: Commit**
  ```bash
  git add docs/data/bdl.md pipeline/bdl_fields.yaml pipeline/data/opolskie.geojson
  git commit -m "docs: rozpoznanie danych BDL dla woj. opolskiego"
  ```

---

### Task 2: Szkielet repo + `species.yaml` + loader

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `forecast/__init__.py`, `pipeline/__init__.py`, `forecast/requirements.txt`, `pipeline/requirements.txt`, `requirements-dev.txt`
- Create: `species.yaml`
- Create: `forecast/species.py`
- Test: `tests/test_species.py`

**Interfaces:**
- Produces (`forecast/species.py`):
  ```python
  @dataclass(frozen=True)
  class Species:
      key: str; name: str
      partners: frozenset[str]            # znormalizowane kody drzew, np. "SO"
      age_min: int; age_opt: int; age_max: int | None
      habitat_preferred: frozenset[str]; habitat_adjacent: frozenset[str]
      season_start: tuple[int, int]; season_end: tuple[int, int]   # (miesiąc, dzień)
      rain_min: float; rain_full: float; soil_moisture_min: float
      temp: tuple[float, float, float, float]   # zero_low, opt_low, opt_high, zero_high
  def load_species(path: Path = ROOT / "species.yaml") -> dict[str, Species]   # kolejność z pliku
  ```

Zależności: `forecast/requirements.txt`: `pyyaml requests jsonschema`; `pipeline/requirements.txt`: `-r ../forecast/requirements.txt geopandas shapely pyogrio`; `requirements-dev.txt`: `pytest responses`. `pyproject.toml`: `[tool.pytest.ini_options] pythonpath = ["."]  testpaths = ["tests"]`. `.gitignore`: `.venv/ __pycache__/ pipeline/data/raw/ pipeline/data/build/ node_modules/`.

`species.yaml` (wartości ze specu §4; `rain_min`/`rain_full`/`soil_moisture_min` domyślnie 10/40/0.15; kody drzew i siedlisk ASCII wielkimi literami — jeśli Task 1 pokazał inne kody BDL, dopasuj normalizację w Task 6, nie te klucze):

| key | name | partners | age min/opt/max | preferred | adjacent | season | temp | rain |
|---|---|---|---|---|---|---|---|---|
| borowik | Borowik szlachetny | SO SW BK DB | 30/50/– | BSW BMSW LMSW LSW | BW BMW LMW LW BS | 07-01–10-31 | 6 12 20 26 | 10/40 |
| podgrzybek | Podgrzybek brunatny | SO SW | 20/30/– | BSW BMSW BW BMW | BS LMSW LMW | 08-01–11-30 | 4 10 18 24 | 10/40 |
| kurka | Kurka | SO SW BK DB | 20/30/– | BSW BMSW BS | BW BMW LMSW | 06-01–10-31 | 8 14 22 28 | 8/30 |
| kozlarz | Koźlarz babka | BRZ | 10/15/– | BMW LMW BW | BMSW LMSW LW BB BMB | 06-01–10-31 | 6 12 20 26 | 10/40 |
| maslak | Maślak zwyczajny | SO | 5/10/40 | BSW BS | BMSW BW | 08-01–11-30 | 4 10 18 24 | 10/40 |
| rydz | Rydz | SO SW | 5/10/40 | LMSW LSW | BMSW LMW LW | 08-01–10-31 | 5 10 18 24 | 10/40 |

- [ ] **Step 1: Write the failing test** `tests/test_species.py`:
  ```python
  def test_load_species_keys_in_order():
      assert list(load_species()) == ["borowik", "podgrzybek", "kurka", "kozlarz", "maslak", "rydz"]
  def test_borowik_values():
      b = load_species()["borowik"]
      assert b.partners == {"SO", "SW", "BK", "DB"} and b.age_max is None
      assert b.temp == (6, 12, 20, 26) and b.season_start == (7, 1) and b.season_end == (10, 31)
      assert b.rain_min == 10 and b.rain_full == 40 and b.soil_moisture_min == 0.15
  def test_maslak_age_max():
      assert load_species()["maslak"].age_max == 40
  def test_preferred_and_adjacent_disjoint():
      for s in load_species().values():
          assert not (s.habitat_preferred & s.habitat_adjacent)
  ```
- [ ] **Step 2:** `python -m venv .venv && .venv/bin/pip install -r pipeline/requirements.txt -r requirements-dev.txt`; `.venv/bin/pytest tests/test_species.py -v` → FAIL (ImportError).
- [ ] **Step 3:** Utwórz pliki konfiguracyjne, `species.yaml` wg tabeli, `forecast/species.py` (domyślne wartości `rain_*`/`soil_moisture_min`, gdy brak w YAML).
- [ ] **Step 4:** `.venv/bin/pytest tests/test_species.py -v` → PASS.
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: szkielet repo i reguły gatunków"`

---

### Task 3: Model pogodowy `forecast/model.py`

**Files:**
- Create: `forecast/model.py`
- Test: `tests/test_model.py`

**Interfaces:**
- Consumes: `Species` (Task 2).
- Produces:
  ```python
  @dataclass
  class DailySeries:          # kompletne, bez None (uzupełnia Task 4)
      dates: list[date]; precip: list[float]; soil_temp: list[float]; soil_moisture: list[float]
  @dataclass
  class WeatherComponents: w: float; rain: float; temp: float; season: float
  def rain_factor(s: DailySeries, i: int, sp: Species) -> float      # z karą wilgotności
  def temp_factor(s: DailySeries, i: int, sp: Species) -> float
  def season_factor(day: date, sp: Species) -> float
  def trapezoid(x: float, a: float, b: float, c: float, d: float) -> float
  def weather_multiplier(s: DailySeries, i: int, sp: Species) -> WeatherComponents  # day = s.dates[i]
  ```

Reguły (spec §4.2): `P = Σ_{k=5..21} wk·precip[i−k]` (indeksy < 0 pomijane), `wk = 1.0` dla k∈7..14, inaczej `0.5`; `rain = clamp((P−rain_min)/(rain_full−rain_min), 0, 1)`; ×0.5, gdy średnia `soil_moisture[i−3..i−1] < soil_moisture_min` (brak indeksów → bez kary). `temp = trapezoid(mean(soil_temp[i−5..i−1]), *sp.temp)` (brak indeksów → `soil_temp[i]`). Sezon: 1.0 w `[start, end]`; poza nim `0.1 + 0.9·(1 − n/14)` dla n dni od granicy, n ≤ 14; dalej 0.1. `w = rain·temp·season`.

Fixture w teście: `series(precip_by_k: dict[int, float], temp=15.0, moist=0.3, day=date(2026, 8, 15))` — buduje 30 dni wstecz + 7 do przodu, `i` = indeks `day`.

- [ ] **Step 1: Write the failing tests** `tests/test_model.py`:
  ```python
  B = load_species()["borowik"]
  def test_rain_40mm_in_core_window_is_full():   assert rain_factor(*series({10: 40}), B) == 1.0
  def test_rain_40mm_at_k5_half_weight():         assert rain_factor(*series({5: 40}), B) == pytest.approx(1/3)
  def test_rain_outside_window_ignored():         assert rain_factor(*series({3: 100, 25: 100}), B) == 0.0
  def test_dry_soil_halves_rain():                assert rain_factor(*series({10: 40}, moist=0.1), B) == 0.5
  @pytest.mark.parametrize("t,exp", [(15, 1.0), (9, 0.5), (23, 0.5), (3, 0.0), (30, 0.0)])
  def test_temp_trapezoid(t, exp):                assert temp_factor(*series({}, temp=t), B) == pytest.approx(exp)
  @pytest.mark.parametrize("d,exp", [(date(2026,8,15),1.0), (date(2026,6,24),0.55), (date(2026,6,10),0.1),
                                     (date(2026,11,7),0.55), (date(2026,7,1),1.0), (date(2026,10,31),1.0)])
  def test_season(d, exp):                        assert season_factor(d, B) == pytest.approx(exp)
  def test_drought_scenario():                    assert weather_multiplier(*series({}), B).w < 0.1
  def test_after_rain_scenario():                 assert weather_multiplier(*series({10: 40}), B).w > 0.8
  def test_frost_scenario():                      assert weather_multiplier(*series({10: 40}, temp=-2), B).w == 0.0
  def test_first_day_without_history_does_not_crash():
      s, _ = series({}); assert weather_multiplier(s, 0, B).rain == 0.0
  ```
  (`series(...)` zwraca `(s, i)`.)
- [ ] **Step 2:** `.venv/bin/pytest tests/test_model.py -v` → FAIL (ImportError).
- [ ] **Step 3:** Zaimplementuj `forecast/model.py` wg sygnatur i reguł powyżej.
- [ ] **Step 4:** `.venv/bin/pytest tests/test_model.py -v` → PASS.
- [ ] **Step 5: Commit** `git add forecast/model.py tests/test_model.py && git commit -m "feat: mnożnik pogodowy"`

---

### Task 4: Klient Open-Meteo `forecast/weather.py`

**Files:**
- Create: `forecast/weather.py`
- Create: `tests/fixtures/openmeteo_two_points.json` (odpowiedź-lista dla 2 punktów, 3 dni, z kilkoma `null`)
- Test: `tests/test_weather.py`

**Interfaces:**
- Consumes: `DailySeries` (Task 3).
- Produces:
  ```python
  API_URL = "https://api.open-meteo.com/v1/forecast"
  class WeatherError(Exception): ...
  def daily_from_response(obj: dict) -> DailySeries
  def fetch_series(points: list[tuple[str, float, float]], *, batch: int = 50,
                   retries: int = 3, sleep=time.sleep, session=None) -> dict[str, DailySeries]
  ```

Szczegóły: współrzędne wsadowo przecinkami (`latitude=50.65,50.75`), odpowiedź dla wielu punktów to lista w kolejności zapytania (dla jednego punktu — obiekt; obsłuż oba). Godzinowe zmienne → średnia dobowa po dacie z `hourly.time[:10]`, ignorując `null`. Dzień bez danych: opad 0, temperatura/wilgotność z najbliższego dnia z danymi (remis → wcześniejszy). Ponowienia: `sleep(1)`, `sleep(2)`, potem `WeatherError`. Timeout żądania 30 s.

- [ ] **Step 1: Write the failing tests** `tests/test_weather.py`:
  ```python
  def test_daily_aggregates_hourly_ignoring_nulls():
      s = daily_from_response(fixture()[0])
      assert s.dates == [date(2026,10,1), date(2026,10,2), date(2026,10,3)]
      assert s.soil_temp[0] == pytest.approx(<średnia nie-null z fixture>)
  def test_missing_day_filled_from_nearest():          # dzień 2 w fixture ma same null
      s = daily_from_response(fixture()[0]); assert s.soil_temp[1] == s.soil_temp[0]; assert s.precip[1] == 0.0
  @responses.activate
  def test_fetch_maps_points_in_order(): ...           # 2 punkty → klucze "a", "b", wartości z fixture
  @responses.activate
  def test_fetch_retries_then_succeeds(): ...          # 500, 500, 200 → sukces; sleep wywołany z 1, 2
  @responses.activate
  def test_fetch_raises_after_retries(): ...           # 4× 500 → WeatherError
  @responses.activate
  def test_fetch_sends_required_params(): ...          # past_days=30, forecast_days=7, timezone=Europe/Warsaw,
                                                       # daily=precipitation_sum, hourly=soil_temperature_6cm,soil_moisture_3_to_9cm
  ```
- [ ] **Step 2:** `.venv/bin/pytest tests/test_weather.py -v` → FAIL.
- [ ] **Step 3:** Zaimplementuj `forecast/weather.py`.
- [ ] **Step 4:** `.venv/bin/pytest tests/test_weather.py -v` → PASS.
- [ ] **Step 5: Commit** `git add forecast/weather.py tests/ && git commit -m "feat: klient Open-Meteo"`

---

### Task 5: `pogoda.json` — schemat, budowa, zapis atomowy, CLI

**Files:**
- Create: `schema/pogoda.schema.json`
- Create: `forecast/run.py`
- Create: `tests/fixtures/pogoda.json` (komórki `506_178` i `507_178`, 6 gatunków, 7 dni — współdzielony z testami JS w Task 9)
- Create: `tests/fixtures/grid.json` (komórki `506_178`, `507_178`)
- Test: `tests/test_run.py`

**Interfaces:**
- Consumes: `load_species` (T2), `weather_multiplier`, `DailySeries` (T3), `fetch_series`, `WeatherError` (T4); `grid.json` (format z Task 7).
- Produces:
  ```python
  def build_payload(cells: list[dict], series: dict[str, DailySeries], species: dict[str, Species],
                    today: date, now: datetime) -> dict
  def write_atomic(payload: dict, out: Path, schema: Path = ROOT / "schema/pogoda.schema.json") -> None
  def main(argv: list[str] | None = None) -> int   # --grid PATH --out PATH; 0 ok, 1 błąd
  ```
  Format zgodny ze spec §5: `generated_at` ISO 8601 z offsetem Europe/Warsaw, `days` = 7 dat od `today`, `cells[cell_id][species] = {w, rain, temp, season}` — każda lista 7 floatów zaokrąglonych do 3 miejsc. Schemat: wymagane `generated_at`, `days` (dokładnie 7, format date), `cells` (obiekt; każdy gatunek wymaga 4 tablic o długości 7, liczby 0–1).

Uruchomienie: `python -m forecast.run --grid web/data/grid.json --out /out/pogoda.json`. Zapis: `out.with_suffix(".tmp")` → walidacja → `os.replace`. Log na stdout (`logging`, poziom INFO).

- [ ] **Step 1: Write the failing tests** `tests/test_run.py`:
  ```python
  def test_payload_shape_and_days(): p = build_payload(...today=date(2026,10,3)...)
      assert p["days"][0] == "2026-10-03" and len(p["days"]) == 7
      assert set(p["cells"]["506_178"]) == {"borowik","podgrzybek","kurka","kozlarz","maslak","rydz"}
  def test_payload_validates_against_schema(): jsonschema.validate(build_payload(...), schema)
  def test_shared_fixture_validates(): jsonschema.validate(json.load(open("tests/fixtures/pogoda.json")), schema)
  def test_write_atomic_replaces_file(tmp_path): ...    # brak .tmp po zapisie, treść nowa
  def test_write_atomic_rejects_invalid_and_keeps_old(tmp_path):
      out.write_text('{"old": 1}'); with pytest.raises(jsonschema.ValidationError): write_atomic({"bad": 1}, out)
      assert out.read_text() == '{"old": 1}'
  def test_main_returns_1_and_keeps_old_on_weather_error(tmp_path, monkeypatch):
      monkeypatch.setattr(run, "fetch_series", raising(WeatherError)); assert main([...]) == 1  # stary plik bez zmian
  ```
- [ ] **Step 2:** `.venv/bin/pytest tests/test_run.py -v` → FAIL.
- [ ] **Step 3:** Utwórz schemat, oba fixture'y (fixture `pogoda.json` wygeneruj `build_payload` na syntetycznych seriach i zapisz), `forecast/run.py`.
- [ ] **Step 4:** `.venv/bin/pytest -v` → wszystkie PASS.
- [ ] **Step 5: Commit** `git add schema forecast/run.py tests && git commit -m "feat: generowanie pogoda.json"`

---

### Task 6: Ocena siedliska `pipeline/habitat.py`

**Files:**
- Create: `pipeline/habitat.py`
- Test: `tests/test_habitat.py`

**Interfaces:**
- Consumes: `Species` (T2).
- Produces:
  ```python
  @dataclass(frozen=True)
  class Stand: sp_main: str; sp_admix: tuple[str, ...]; age: int | None; hab: str | None
  def normalize_species_code(raw: str) -> str      # strip, upper, część przed ".", diakrytyki → ASCII (Ś→S, Ł→L…)
  def normalize_habitat(raw: str | None) -> str | None   # strip, upper, diakrytyki → ASCII, "" → None
  def partner_factor(st: Stand, sp: Species) -> float    # 1.0 panujący / 0.6 domieszka / 0.0
  def age_factor(age: int | None, sp: Species) -> float  # None → 0.5
  def habitat_factor(hab: str | None, sp: Species) -> float  # None → 1.0; pref 1.0; adj 0.6; inne 0.2
  def habitat_score(st: Stand, sp: Species) -> float     # iloczyn, 0–1
  ```
  `Stand` przyjmuje kody już znormalizowane. Wiek (spec §4.1): `< age_min` → 0; `age_min..age_opt` liniowo 0.3→1.0; `> age_max` liniowo 1.0→0.3 przez 20 lat, dalej 0.3.

- [ ] **Step 1: Write the failing tests** `tests/test_habitat.py`:
  ```python
  S = load_species()
  def test_old_pine_fresh_forest_high_for_podgrzybek(): assert habitat_score(Stand("SO", (), 80, "BSW"), S["podgrzybek"]) == 1.0
  def test_alder_zero_for_all(): assert all(habitat_score(Stand("OL", (), 60, "OL"), s) == 0 for s in S.values())
  def test_young_pine_good_for_maslak_not_borowik():
      st = Stand("SO", (), 15, "BSW"); assert habitat_score(st, S["maslak"]) == 1.0; assert habitat_score(st, S["borowik"]) == 0.0
  def test_admixture_partner(): assert habitat_score(Stand("OL", ("SW",), 60, "LMSW"), S["borowik"]) == pytest.approx(0.6)
  @pytest.mark.parametrize("age,exp", [(40, 0.65), (30, 0.3), (29, 0.0), (None, 0.5)])
  def test_age_borowik(age, exp): assert age_factor(age, S["borowik"]) == pytest.approx(exp)
  @pytest.mark.parametrize("age,exp", [(40, 1.0), (50, 0.65), (70, 0.3)])
  def test_age_maslak_decline(age, exp): assert age_factor(age, S["maslak"]) == pytest.approx(exp)
  def test_habitat_levels(): b = S["borowik"]; assert (habitat_factor("BSW", b), habitat_factor("BW", b), habitat_factor("OL", b), habitat_factor(None, b)) == (1.0, 0.6, 0.2, 1.0)
  @pytest.mark.parametrize("raw,exp", [(" db.s ", "DB"), ("ŚW", "SW"), ("so", "SO"), ("BRZ", "BRZ")])
  def test_normalize_species(raw, exp): assert normalize_species_code(raw) == exp
  @pytest.mark.parametrize("raw,exp", [("BMśw", "BMSW"), ("  ", None), (None, None)])
  def test_normalize_habitat(raw, exp): assert normalize_habitat(raw) == exp
  ```
- [ ] **Step 2:** `.venv/bin/pytest tests/test_habitat.py -v` → FAIL.
- [ ] **Step 3:** Zaimplementuj `pipeline/habitat.py`. Jeśli Task 1 pokazał kody BDL nieobsłużone przez normalizację, dodaj przypadki do testu parametryzowanego i obsługę.
- [ ] **Step 4:** `.venv/bin/pytest tests/test_habitat.py -v` → PASS.
- [ ] **Step 5: Commit** `git add pipeline/habitat.py tests/test_habitat.py && git commit -m "feat: ocena siedliska"`

---

### Task 7: Siatka pogodowa `pipeline/grid.py`

**Files:**
- Create: `pipeline/grid.py`
- Test: `tests/test_grid.py`

**Interfaces:**
- Produces:
  ```python
  STEP = 0.1
  def cell_id(lat: float, lon: float) -> str            # f"{floor(round(lat*10,6))}_{floor(round(lon*10,6))}"
  def cell_center(cid: str) -> tuple[float, float]      # ((idx+0.5)*STEP) dla obu osi, zaokr. do 2 miejsc
  def build_grid(points: Iterable[tuple[float, float]]) -> dict   # {"step": 0.1, "cells": [{"id","lat","lon"}]} unikalne, posortowane po id
  ```
  `grid.json` = wynik `build_grid` zapisany przez Task 8; czyta go `forecast/run.py` (Task 5: `cells` = `grid["cells"]`, punkty `(id, lat, lon)`).

- [ ] **Step 1: Write the failing tests** `tests/test_grid.py`:
  ```python
  def test_cell_id_basic(): assert cell_id(50.67, 17.93) == "506_179"
  def test_cell_id_float_edge(): assert cell_id(50.6, 17.9) == "506_179"   # bez błędu 505.999
  def test_cell_center(): assert cell_center("506_179") == (50.65, 17.95)
  def test_build_grid_unique_sorted():
      g = build_grid([(50.67, 17.93), (50.61, 17.99), (50.71, 17.93)])
      assert [c["id"] for c in g["cells"]] == ["506_179", "507_179"] and g["step"] == 0.1
  ```
- [ ] **Step 2:** `.venv/bin/pytest tests/test_grid.py -v` → FAIL.
- [ ] **Step 3:** Zaimplementuj `pipeline/grid.py`.
- [ ] **Step 4:** `.venv/bin/pytest tests/test_grid.py -v` → PASS.
- [ ] **Step 5: Commit** `git add pipeline/grid.py tests/test_grid.py && git commit -m "feat: siatka pogodowa"`

---

### Task 8: Wczytanie BDL i budowa kafelków

**Files:**
- Create: `pipeline/fetch_bdl.py`, `pipeline/build_tiles.py`, `pipeline/Dockerfile`
- Test: `tests/test_build_tiles.py`, `tests/test_fetch_bdl.py`

**Interfaces:**
- Consumes: `bdl_fields.yaml`, `opolskie.geojson` (T1), `Stand`, `normalize_*`, `habitat_score` (T6), `cell_id`, `build_grid` (T7), `load_species` (T2).
- Produces:
  ```python
  # fetch_bdl.py
  def load_bdl(src: Path, fields: dict) -> GeoDataFrame   # kolumny: id, sp_main, sp_admix (tuple), age (Int64), hab, geometry; EPSG:4326; tylko drzewostany
  def main(argv=None) -> int                               # pobiera dane wg bdl_fields.yaml do pipeline/data/raw/ (lub instrukcja ręczna z docs/data/bdl.md)
  # build_tiles.py
  def compute_features(gdf: GeoDataFrame, species: dict[str, Species], boundary=None) -> GeoDataFrame
      # + kolumny: cell, lat, lon (z representative_point), h_<key> (int 0–100); przycięcie do boundary
  def write_centroids(gdf: GeoDataFrame, keys: list[str], path: Path, threshold: int = 40) -> int  # liczba wierszy
  def main(argv=None) -> int   # --bdl DIR --boundary GEOJSON --out web/data
  ```
  `main` w `build_tiles.py`: `load_bdl` → `compute_features` → zapis `pipeline/data/build/lasy.geojsonseq` (atrybuty: `id, cell, sp, age, hab, h_*`) → `tippecanoe -o web/data/lasy.pmtiles -l lasy -Z8 -z14 --drop-smallest-as-needed --force <in>` → `web/data/centroidy.json` (format spec §5, lat/lon zaokr. do 5 miejsc) → `web/data/grid.json` (`build_grid` z lat/lon wszystkich wydzieleń).
  `pipeline/Dockerfile`: `FROM python:3.12-slim`, buduje tippecanoe ze źródeł (tag ≥ 2.17), instaluje `pipeline/requirements.txt`; uruchamianie: `docker build -f pipeline/Dockerfile -t grzyby-pipeline . && docker run --rm -v $PWD:/w -w /w grzyby-pipeline python -m pipeline.build_tiles --bdl pipeline/data/raw --boundary pipeline/data/opolskie.geojson --out web/data`.

- [ ] **Step 1: Write the failing tests** (syntetyczny GeoDataFrame, bez plików BDL):
  ```python
  # tests/test_build_tiles.py
  def test_h_columns_and_values(): f = compute_features(gdf([Stand("SO",(),80,"BSW")]), S)
      assert f.loc[0, "h_podgrzybek"] == 100 and f.loc[0, "h_borowik"] == 100 and f.loc[0, "h_kozlarz"] == 0
  def test_cell_from_representative_point():   # polygon w kształcie litery C, centroid poza nim, w innej komórce
      f = compute_features(gdf_from(c_shape), S); assert f.loc[0, "cell"] == cell_id(*rep_point_latlon(c_shape))
  def test_clipped_to_boundary(): ...           # polygon w połowie poza granicą → pole zmniejszone, poza → usunięty
  def test_centroids_threshold(tmp_path):       # rekordy z max(h)=39 i 40 → zapisany tylko 40
      assert write_centroids(f, KEYS, p) == 1 and json.load(open(p))["species"] == KEYS
  # tests/test_fetch_bdl.py
  def test_load_bdl_maps_and_filters(tmp_path): # zapisz mały GPKG z kolumnami wg fields i 1 rekordem nieleśnym
      g = load_bdl(tmp_path, fields); assert list(g.columns[:5]) == ["id","sp_main","sp_admix","age","hab"]; assert len(g) == 1
      assert g.crs.to_epsg() == 4326 and g.loc[0, "sp_main"] == "SW"   # z "ŚW"
  ```
- [ ] **Step 2:** `.venv/bin/pytest tests/test_build_tiles.py tests/test_fetch_bdl.py -v` → FAIL.
- [ ] **Step 3:** Zaimplementuj `fetch_bdl.py` (mapowanie z `bdl_fields.yaml`, normalizacja z T6, `to_crs(4326)`) i `build_tiles.py`.
- [ ] **Step 4:** Testy → PASS.
- [ ] **Step 5:** Pobierz dane wszystkich nadleśnictw (`python -m pipeline.fetch_bdl`), zbuduj obraz i uruchom pipeline (polecenie wyżej). Oczekiwane: `web/data/lasy.pmtiles` (zanotuj rozmiar; > 50 MB → `git lfs track "web/data/*.pmtiles"`), `centroidy.json`, `grid.json` z ~70–150 komórkami. Sprawdź `pmtiles show web/data/lasy.pmtiles` → warstwa `lasy`, minzoom 8, maxzoom 14.
- [ ] **Step 6: Commit**
  ```bash
  git add pipeline tests web/data && git commit -m "feat: pipeline BDL → PMTiles, centroidy, siatka"
  ```

---

### Task 9: Logika frontendu (testowalna w Node)

**Files:**
- Create: `web/js/data.js`, `web/js/ranking.js`, `web/js/hash.js`
- Test: `web/tests/data.test.js`, `web/tests/ranking.test.js`, `web/tests/hash.test.js`

**Interfaces:**
- Consumes: `tests/fixtures/pogoda.json` (T5), format `centroidy.json` (T8).
- Produces:
  ```js
  // data.js
  export const SPECIES = [{key:"borowik", name:"Borowik szlachetny"}, …6]   // kolejność z Global Constraints
  export function weatherFor(pogoda, cell, species, dayIdx)   // {w,rain,temp,season} | null (brak pogody/komórki)
  export function score(hInt, w)                              // Math.round(hInt * w); w == null → null
  export function scoreClass(score)                           // null→null; <10→0; <25→1; <45→2; <=65→3; >65→4
  export function isStale(generatedAtIso, now = new Date())   // > 36 h
  export function availableDays(days, todayIso)               // [{date, idx}] tylko date >= todayIso
  export async function loadData(base = "data/")              // {pogoda: obj|null, centroids}; błąd pogody → null
  // ranking.js
  export function haversineKm(a, b)                           // a,b = {lat, lon}
  export function topN(centroids, pogoda, species, dayIdx, origin, radiusKm = 20, n = 10)
      // → [{id, lat, lon, score}] score malejąco, remis → id rosnąco; pomija null i score 0
  // hash.js
  export function parseHash(hash)    // "#s=kurka&d=2&z=11&c=50.67,17.93" → {species, day, zoom, center:[lon,lat]}; złe/brak → domyślne {species:"borowik", day:0}
  export function formatHash(state)
  ```

- [ ] **Step 1: Write the failing tests** (`node:test` + `node:assert/strict`; fixture czytany przez `fs.readFileSync` z `../../tests/fixtures/pogoda.json`):
  ```js
  test("weatherFor missing cell → null", () => assert.equal(weatherFor(P, "999_999", "borowik", 0), null))
  test("weatherFor null pogoda → null", () => assert.equal(weatherFor(null, "506_178", "borowik", 0), null))
  test("score", () => { assert.equal(score(80, 0.5), 40); assert.equal(score(80, null), null) })
  test("scoreClass bounds", () => assert.deepEqual([9,10,25,45,65,66].map(scoreClass), [0,1,2,3,3,4]))
  test("isStale 36h", () => { assert.equal(isStale("2026-10-01T05:00:00+02:00", new Date("2026-10-02T17:00:00+02:00")), false)
                              assert.equal(isStale("2026-10-01T05:00:00+02:00", new Date("2026-10-02T17:01:00+02:00")), true) })
  test("availableDays drops past", () => assert.deepEqual(availableDays(["2026-10-02","2026-10-03","2026-10-04"], "2026-10-03").map(d=>d.idx), [1,2]))
  test("haversine Opole–Wrocław ≈ 79 km", () => assert.ok(Math.abs(haversineKm({lat:50.675,lon:17.921},{lat:51.11,lon:17.032}) - 79) < 2))
  test("topN radius, order, ties, skips missing cell", () => { … })
  test("parseHash roundtrip + invalid species → default", () => { … })
  ```
- [ ] **Step 2:** `node --test web/tests/` → FAIL.
- [ ] **Step 3:** Zaimplementuj trzy moduły (bez zależności od DOM / maplibre).
- [ ] **Step 4:** `node --test web/tests/` → PASS.
- [ ] **Step 5: Commit** `git add web/js web/tests && git commit -m "feat: logika frontendu (wynik, ranking, hash)"`

---

### Task 10: Mapa i interfejs

**Files:**
- Create: `scripts/vendor.sh` (pobiera `maplibre-gl@4.7.1` js+css i `pmtiles@3.2.1` z unpkg do `web/vendor/`; wersje przypięte)
- Create: `web/index.html`, `web/css/app.css`, `web/js/map.js`, `web/js/popup.js`, `web/js/ui.js`

**Interfaces:**
- Consumes: wszystko z T9; `lasy.pmtiles` (T8).
- Produces:
  ```js
  // map.js
  export function createMap(container, {center, zoom, onFeatureClick, onMove})  // MapLibre + protokół pmtiles + podkład OSM raster
  export function fillColorExpression(pogoda, species, dayIdx)  // wyrażenie MapLibre (eksportowane, by dało się je przetestować)
  export function setView(map, pogoda, species, dayIdx)         // setPaintProperty("lasy-fill", "fill-color", …)
  // popup.js
  export function renderPopup(props, weather, speciesKey)        // HTMLElement
  // ui.js
  export function init()                                          // wywoływane z index.html
  ```
  `fillColorExpression`: `wv = ["match", ["get","cell"], <cell>, <w>, …, -1]`; jeśli `pogoda == null` → kolor z samego `h` (te same progi); jeśli `wv < 0` → szary `#9e9e9e` z `fill-opacity` 0.3 („brak danych”); inaczej `step` po `round(h × wv)` z progami 10/25/45/65 i 5 kolorami (szary, jasnożółty, żółty, pomarańczowy, czerwony). Kontur `line` widoczny od zoom 12.
  Popup: adres leśny, gatunek panujący, wiek, typ siedliskowy, wynik i składowe (siedlisko %, opad, temperatura, sezon jako 0–100%).
  UI: górny pasek (`<select>` gatunku, ◀ data ▶ wg `availableDays`), przycisk lokalizacji, dolny panel „Top 10 w promieniu 20 km” (od GPS lub środka mapy po `moveend`), żółty pasek przy `isStale`, komunikat „Brak danych pogodowych” przy `pogoda == null`, stopka „Model heurystyczny, bez kalibracji” + atrybucja OSM, BDL, Open-Meteo. Stan w hashu (`hash.js`).

- [ ] **Step 1: Write the failing test** `web/tests/map.test.js`:
  ```js
  test("expression contains match on cell with fallback -1", () => { const e = JSON.stringify(fillColorExpression(P, "borowik", 0)); assert.ok(e.includes('"match"') && e.includes('"cell"') && e.includes('-1')) })
  test("expression without pogoda uses h only", () => assert.ok(!JSON.stringify(fillColorExpression(null, "borowik", 0)).includes('"match"')))
  ```
  (map.js nie może importować maplibre na poziomie modułu — korzysta z globalnego `maplibregl` dopiero w `createMap`.)
- [ ] **Step 2:** `node --test web/tests/` → FAIL. Uruchom `scripts/vendor.sh`.
- [ ] **Step 3:** Zaimplementuj moduły, `index.html`, `app.css` (mobile-first, panel dolny wysuwany).
- [ ] **Step 4:** `node --test web/tests/` → PASS. Ręcznie: `cp tests/fixtures/pogoda.json web/data/live/` (z datami przesuniętymi na dziś), `python -m http.server -d web 8000` (obsługuje Range). Sprawdź w przeglądarce (szerokość 390 px i desktop): kolorowanie, zmiana gatunku/dnia bez przeładowania kafelków, popup, ranking, link z hashem, pasek nieaktualności (zmień `generated_at`), brak pliku pogody.
- [ ] **Step 5: Commit** `git add scripts web && git commit -m "feat: mapa i interfejs"` (`web/data/live/` w `.gitignore`).

---

### Task 11: Wdrożenie — Docker Compose na Coolify

**Files:**
- Create: `Dockerfile.web`, `forecast/Dockerfile`, `forecast/crontab`, `forecast/entrypoint.sh`, `nginx.conf`, `docker-compose.yml`, `README.md`
- Test: `tests/test_healthcheck.py`

**Interfaces:**
- Consumes: `forecast.run.main` (T5), `web/` (T8–T10).
- Produces: `forecast/healthcheck.py`: `def is_fresh(path: Path, max_age_h: float = 36, now: float | None = None) -> bool`; `__main__` → exit 0/1.

Konfiguracja:
- `Dockerfile.web`: `nginx:1.27-alpine`, `COPY web /usr/share/nginx/html`, `COPY nginx.conf /etc/nginx/conf.d/default.conf`.
- `nginx.conf`: `gzip on; gzip_types application/json text/css application/javascript;` `location /data/live/ { add_header Cache-Control "no-cache"; }` `location ~* \.(pmtiles)$ { add_header Cache-Control "public, max-age=86400"; }` `location /vendor/ { add_header Cache-Control "public, max-age=31536000, immutable"; }` `types { application/octet-stream pmtiles; }` (Range działa domyślnie).
- `forecast/Dockerfile`: `python:3.12-slim`, `ARG TARGETARCH`, supercronic v0.2.33 z GitHub releases dla `${TARGETARCH}`, `pip install -r forecast/requirements.txt`, `COPY species.yaml schema forecast web/data/grid.json`, `ENV TZ=Europe/Warsaw`, `HEALTHCHECK CMD python -m forecast.healthcheck /out/pogoda.json`.
- `forecast/crontab`: `0 5,14 * * * python -m forecast.run --grid /app/web/data/grid.json --out /out/pogoda.json`.
- `entrypoint.sh`: jeden przebieg `forecast.run` (błąd nie przerywa startu), potem `exec supercronic /app/forecast/crontab`.
- `docker-compose.yml`: usługi `web` (build `Dockerfile.web`, wolumen `weather:/usr/share/nginx/html/data/live:ro`, `expose: 80`) i `forecast` (build `forecast/Dockerfile`, wolumen `weather:/out`, `restart: unless-stopped`); wolumen `weather`. Bez `ports:` — routing robi Coolify.
- `README.md`: uruchomienie testów, pipeline, lokalny `docker compose up`, konfiguracja w Coolify (zasób Docker Compose z repo, domena na usłudze `web`).

- [ ] **Step 1: Write the failing test** `tests/test_healthcheck.py`:
  ```python
  def test_fresh(tmp_path): p = touch(tmp_path, age_h=35); assert is_fresh(p) is True
  def test_stale(tmp_path): p = touch(tmp_path, age_h=37); assert is_fresh(p) is False
  def test_missing(tmp_path): assert is_fresh(tmp_path / "nope.json") is False
  ```
- [ ] **Step 2:** `.venv/bin/pytest tests/test_healthcheck.py -v` → FAIL.
- [ ] **Step 3:** Zaimplementuj `forecast/healthcheck.py` i pliki konfiguracyjne.
- [ ] **Step 4:** `.venv/bin/pytest -v && node --test web/tests/` → wszystko PASS.
- [ ] **Step 5: Smoke** `docker compose up --build -d`, potem `docker compose exec web wget -qO- localhost/data/live/pogoda.json | head -c 200` → JSON z `generated_at` z dzisiaj; `docker compose exec web wget -S --header="Range: bytes=0-15" -qO- localhost/data/lasy.pmtiles 2>&1 | grep "206"`; `docker compose ps` → `forecast` healthy. `docker compose down`.
- [ ] **Step 6: Commit** `git add -A && git commit -m "feat: wdrożenie Docker Compose dla Coolify"`
- [ ] **Step 7:** Wdrożenie na Coolify wymaga zdalnego repo i dostępu do panelu — przekaż użytkownikowi instrukcję z README; nie pushuj bez jego zgody.
