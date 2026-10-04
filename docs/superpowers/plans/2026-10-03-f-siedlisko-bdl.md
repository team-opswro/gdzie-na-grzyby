# F. Dodatkowe czynniki siedliska z BDL — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `h` uwzględnia runo, wilgotność, degradację, grupę gleby, uszkodzenie i zadrzewienie jako modyfikatory z dolnym ograniczeniem, parametryzowane w `species.yaml`.

**Architecture:** `forecast/species.py` parsuje tabele czynników (`factors_default` + nadpisania gatunkowe) do `Species.factors`; `pipeline/habitat.py` liczy czynniki z nowych pól `Stand` i wpina je w rejestr ze specu H (`habitat_components`, `habitat_score(neutral=…)`); `pipeline/ingest.py` dostarcza pola z DuckDB; `build_tiles` buduje `Stand` przez `stand_from_row`.

**Tech Stack:** Python 3, DuckDB, geopandas, pytest.

**Spec:** `docs/superpowers/specs/2026-10-03-f-siedlisko-bdl-design.md`

**Zależność:** plan H, Task 1 (rejestr czynników: `habitat_components`, `habitat_score(st, sp, neutral)`, `HABITAT_FACTORS`, `stand_from_row`) musi być wykonany wcześniej. Pełna walidacja (Task 4, krok 5) wymaga ukończonego planu H.

## Global Constraints

- Komentarze, komunikaty, commity po polsku (`feat(pipeline): …`).
- `h = partner × habitat_factor × max(MOD_FLOOR, Π czynników)`, `MOD_FLOOR = 0.4`; brak danych lub kod spoza tabeli → czynnik 1.0.
- Kody normalizowane `_ascii_upper` (`Ś`→`S`, `Ł`→`L`); klucze tabel w `species.yaml` ASCII, wielkie litery.
- Nadpisanie gatunkowe zastępuje całą tabelę czynnika (bez scalania kluczy).
- Mnożniki w tabelach ∈ [0, 1]; nieznana nazwa czynnika → `ValueError` przy ładowaniu.
- Wartości startowe dokładnie jak w spec §4.3.
- Kontrakt kafelków bez zmian (te same `h_*` 0–100).
- Testy: `.venv/bin/pytest -q`.

## Review Focus

1. **Stary `Stand(...)` bez nowych pól** (testy, źródło API/Wieluń) — wynik identyczny jak przed planem. Test w Task 2.
2. **Kod z polską literą w danych** (`Ś`, `ŚCIO`, `SŚ`) — trafia w klucz ASCII tabeli. Test w Task 3.
3. **`damage_degree`/`density_cd` jako tekst z spacjami lub pusty** (`" 20"`, `""`) — liczba albo `None`, bez wyjątku. Test w Task 3.
4. **Gatunek bez sekcji `factors`** — dziedziczy wszystkie tabele domyślne. Test w Task 1.
5. **Ablacja czynnika w raporcie H** — `neutral={"veg"}` zmienia wynik tylko przez `veg`, a `MOD_FLOOR` liczy się z pozostałych. Test w Task 2.

---

### Task 1: Parsowanie czynników w `forecast/species.py`

**Files:**
- Modify: `forecast/species.py`
- Test: `tests/test_species.py`

**Interfaces:**
- Produces:
  - `TABLE_FACTORS = ("veg", "moist", "degr", "soil")`, `RAMP_FACTORS = ("damage",)`, `BAND_FACTORS = ("density",)`, `FACTOR_NAMES = TABLE_FACTORS + RAMP_FACTORS + BAND_FACTORS` (spec I dopisze `twi`, `exposure` do `TABLE_FACTORS`).
  - `Species.factors: Mapping[str, object]` (pole z `default_factory`, żeby istniejące konstrukcje `Species(...)` w testach działały): tabela → `dict[str, float]`; `damage` → `Ramp(full: float, zero_at: float, min: float)`; `density` → `tuple[tuple[float, float], ...]` (górna granica włącznie, mnożnik), posortowane po granicy.
  - `load_species(path)` czyta `factors_default` z korzenia YAML-a i przekazuje do `_parse(key, d, defaults)`; brak `factors_default` → pusty słownik (wszystkie czynniki neutralne).

- [ ] **Step 1: Testy**

```python
def test_factors_default_inherited(tmp_path):
    # YAML z factors_default.veg {ZAD: 0.7} i gatunkiem bez factors -> sp.factors["veg"] == {"ZAD": 0.7}
def test_species_override_replaces_table(tmp_path):
    # factors_default.degr {Z1: 0.9, N1: 1.0}; gatunek factors.degr {} -> sp.factors["degr"] == {}
def test_ramp_and_bands_parsed(tmp_path):
    # damage {full: 40, zero_at: 100, min: 0.6} -> Ramp(40, 100, 0.6)
    # density [[0.9, 1.0], [0.4, 0.8], [1.0, 0.9]] -> ((0.4, 0.8), (0.9, 1.0), (1.0, 0.9))
def test_unknown_factor_raises(tmp_path):      # factors_default.foo -> ValueError
def test_multiplier_out_of_range_raises(tmp_path):  # veg {ZAD: 1.2} -> ValueError; min 1.5 w rampie -> ValueError
def test_repo_species_yaml_loads():            # load_species() z repo nie rzuca
```

- [ ] **Step 2: Uruchom** `.venv/bin/pytest tests/test_species.py -q` — FAIL (brak `factors`).
- [ ] **Step 3: Implementacja** wg Interfaces.
- [ ] **Step 4: Uruchom** `.venv/bin/pytest -q` — PASS.
- [ ] **Step 5: Commit** `feat(forecast): tabele czynników siedliska w species.yaml`

---

### Task 2: Czynniki w `pipeline/habitat.py`

**Files:**
- Modify: `pipeline/habitat.py`
- Test: `tests/test_habitat.py`

**Interfaces:**
- Consumes: `Species.factors`, `Ramp` (Task 1); rejestr z planu H Task 1.
- Produces:
  - `Stand` — nowe pola na końcu, wszystkie `= None`: `moist: str | None`, `degr: str | None`, `soil: str | None`, `veg: str | None`, `damage: int | None`, `density: float | None`.
  - `MOD_FLOOR = 0.4`
  - `soil_group(code: str | None) -> str | None` — wiodące wielkie litery kodu oryginalnego przed normalizacją małych liter (`"BRk"`→`"BR"`, `"RDb"`→`"RD"`, `"Bgw"`→`"B"`, `"OGw"`→`"OG"`, `"MDbr"`→`"MD"`, `"Gms"`→`"G"`, `"Pw"`→`"P"`); `None`/pusty → `None`.
  - `factor_value(name: str, st: Stand, sp: Species) -> float` — tabela: `sp.factors[name].get(wartość, 1.0)` (dla `soil` kluczem jest `soil_group`); rampa `damage`: `≤ full` → 1.0, liniowo do `min` przy `zero_at`, powyżej → `min`; pasma `density`: pierwszy przedział z `value ≤ granica`, powyżej ostatniej → mnożnik ostatniego; `None` lub brak czynnika w `sp.factors` → 1.0.
  - `HABITAT_FACTORS = ("partner", "habitat", "age", *FACTOR_NAMES)`
  - `habitat_components` zwraca także każdy czynnik z `FACTOR_NAMES`.
  - `habitat_score(st, sp, neutral)`: `partner × habitat × max(MOD_FLOOR, Π factor_value(f) dla f ∉ neutral)`.
  - `stand_from_row(..., moist=None, degr=None, soil=None, veg=None, damage=None, density=None) -> Stand` — `damage` zaokrąglane do dziesiątek (`int(round(x, -1))`), `density` do 1 miejsca; `NaN`/`pd.NA` → `None`.

- [ ] **Step 1: Testy**

```python
SP = S["kurka"]  # z repo species.yaml po Task 4; do czasu Task 4 — Species z factors ustawionymi w teście przez dataclasses.replace
def test_old_stand_unchanged():                       # Stand("SO", (), 80, "BSW") -> ten sam wynik co przed planem dla każdego gatunku
def test_veg_factor_from_table():                     # veg="ZAD" -> factor 0.7; veg="XYZ" -> 1.0; veg=None -> 1.0
def test_soil_group():
    assert [soil_group(c) for c in ("BRk", "RDb", "Bgw", "OGw", "MDbr", "Gms", "Pw", None, "")] == \
        ["BR", "RD", "B", "OG", "MD", "G", "P", None, None]
def test_damage_ramp():                               # 40 -> 1.0, 70 -> 0.8, 100 -> 0.6, 120 -> 0.6
def test_density_bands():                             # 0.4 -> 0.8, 0.6 -> 1.0, 1.0 -> 0.9, 1.2 -> 0.9
def test_mod_floor():                                 # 0.7 × 0.4 × 0.8 = 0.224 -> mod 0.4; h = partner × habitat × 0.4
def test_neutral_factor_only_affects_that_factor():   # veg 0.7, moist 0.4: neutral {"veg"} -> mod max(0.4, 0.4); neutral {"moist"} -> 0.7
def test_components_include_all_factors():            # set(habitat_components(...)) == set(HABITAT_FACTORS)
def test_stand_from_row_rounds_damage_and_density():  # damage 23 -> 20, density 0.94 -> 0.9, NaN -> None
```

- [ ] **Step 2: Uruchom** `.venv/bin/pytest tests/test_habitat.py -q` — FAIL.
- [ ] **Step 3: Implementacja** wg Interfaces.
- [ ] **Step 4: Uruchom** `.venv/bin/pytest -q` — PASS.
- [ ] **Step 5: Commit** `feat(pipeline): modyfikatory siedliska z dolnym ograniczeniem`

---

### Task 3: Pola z BDL w ingeście i w `build_tiles`

**Files:**
- Modify: `pipeline/ingest.py` (`STANDS_SQL`, `load_stands`)
- Modify: `pipeline/build_tiles.py` (`compute_features` — przekazanie nowych kolumn do `stand_from_row`)
- Test: `tests/test_ingest.py`, `tests/test_build_tiles.py`, fixture paczki w `tests/fixtures/bdl_pkg/` (dopisać kolumny)

**Interfaces:**
- Consumes: `stand_from_row` (Task 2), `normalize_habitat`/`_ascii_upper` z `habitat.py`.
- Produces: `load_stands` zwraca dodatkowo kolumny `moist`, `degr`, `soil`, `veg` (znormalizowane ASCII; `soil` z zachowaniem wielkości liter — `soil_group` potrzebuje oryginału, normalizowane jest tylko `Ł/Ś`→ASCII bez zmiany wielkości), `damage` (`Int64`), `density` (float lub `NaN`). SQL: `TRIM` na kodach, `TRY_CAST(TRIM(damage_degree) AS INTEGER)`, CTE `dens` jak w spec §3 (pierwszy wiersz `MAIN_STOREYS` wg `CASE storey_cd WHEN 'DRZEW' THEN 0 ELSE 1 END`). Wydzielenia źródła API — kolumny `None`.

- [ ] **Step 1: Testy**

```python
def test_load_stands_new_columns(fixture_db):         # wartości z fixture: moist "SS" (z "SŚ"), veg "SCIO" (z "ŚCIO"), soil "BRk", damage 20, density 0.9
def test_density_from_drzew_before_ip(fixture_db):    # wydzielenie z DRZEW 0.6 i IP 0.9 -> 0.6
def test_blank_numbers_become_none(fixture_db):       # damage "" / " " -> <NA>, density "" -> NaN
def test_compute_features_passes_new_fields():        # GeoDataFrame z veg="ZAD" daje niższe h_kurka niż veg=None
```

- [ ] **Step 2: Uruchom** `.venv/bin/pytest tests/test_ingest.py tests/test_build_tiles.py -q` — FAIL.
- [ ] **Step 3: Implementacja** wg Interfaces.
- [ ] **Step 4: Uruchom** `.venv/bin/pytest -q` — PASS; dodatkowo na prawdziwej bazie: `.venv/bin/python -c "from pipeline.ingest import *; d=load_stands(DEFAULT_DB, DEFAULT_PARQUET); print(len(d), d[['moist','degr','soil','veg','damage','density']].notna().mean().round(2).to_dict())"` — oczekiwane: ~335 tys. wierszy, udziały niepustych zgodne ze spec §2 (moist/degr/soil/veg ≥ 0.97, damage ~0.4, density ~0.4–0.6).
- [ ] **Step 5: Commit** `feat(pipeline): wilgotność, degradacja, gleba, runo, uszkodzenia i zadrzewienie z BDL`

---

### Task 4: Wartości w `species.yaml`, histogram `h`, dokumentacja, walidacja

**Files:**
- Modify: `species.yaml`, `pipeline/build.py` (histogram w `build.json`), `docs/data/api.md`
- Test: `tests/test_species.py`, `tests/test_build.py`, `tests/test_habitat.py`

**Interfaces:**
- Produces: `species.yaml` — `factors_default` (veg, moist, degr, soil `{}`, damage, density) i nadpisania gatunkowe dokładnie wg spec §4.3; `build.json` → `"h_hist": {<gatunek>: [10 liczb]}` (przedziały 0–9, 10–19, …, 90–100).

- [ ] **Step 1: Testy**

```python
def test_yaml_factor_values():                        # S["kozlarz"].factors["moist"]["BO"] == 0.8; S["rydz"].factors["degr"] == {}; S["kurka"].factors["moist"]["WW"] == 0.85
def test_kurka_brown_soil_lower_than_podzol():        # Stand("SO", (), 60, "BSW", soil="BRk") < soil="Bw" dla kurki
def test_build_json_has_h_hist(tmp_path):             # run(...) -> meta["h_hist"]["borowik"] ma 10 elementów, suma == liczba wydzieleń
```

- [ ] **Step 2: Uruchom** — FAIL.
- [ ] **Step 3: Implementacja**; w `docs/data/api.md` przy `h_<gatunek>` dopisać zdanie ze spec §5 i opis `h_hist` w `build.json`.
- [ ] **Step 4: Uruchom** `.venv/bin/pytest -q` — PASS.
- [ ] **Step 5: Walidacja** (wymaga planu H): `.venv/bin/python -m pipeline.validate --no-weather --compare pipeline/data/walidacja/walidacja-baza.json`. Dla każdego czynnika z `FACTOR_NAMES`: jeśli `ablation_auc ≥ auc` dla wszystkich gatunków z wynikiem — ustawić jego tabelę neutralną (`{}` / rampa z `min: 1.0` / pasma z mnożnikami 1.0) i powtórzyć raport. Liczby AUC przed/po i decyzje wpisać do opisu commita.
- [ ] **Step 6: Commit** `feat(pipeline): wartości czynników siedliska i histogram h w build.json`
