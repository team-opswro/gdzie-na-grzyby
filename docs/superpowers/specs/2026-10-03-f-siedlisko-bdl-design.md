# F. Dodatkowe czynniki siedliska z BDL — projekt

Data: 2026-10-03
Status: zaakceptowany (rozmowa 2026-10-03)
Zakres: wykorzystanie w ocenie siedliska `h` pól BDL, które `pipeline.ingest` już ładuje do `bdl.duckdb`, ale model ich nie używa: wilgotność, degradacja, podtyp gleby, pokrywa runa, uszkodzenie drzewostanu, zadrzewienie.
Poza zakresem: zmiana formuły klienta `round(h × w)`, nowe atrybuty w kafelkach, objaśnienie czynników w popupie, czynniki terenowe (spec I).

## 1. Cel

Dziś `h = partner_score × habitat_factor` (`pipeline/habitat.py`). Dwa wydzielenia z tym samym gatunkiem, wiekiem i typem siedliskowym lasu dostają tę samą ocenę, choć jedno jest zatrawione i przegęszczone, a drugie mszyste i luźne. Nowe czynniki różnicują `h` w obrębie tych grup.

**Kryterium sukcesu:** raport `pipeline.validate` (spec H) po zmianie pokazuje AUC siedliska nie gorsze niż linia bazowa dla każdego gatunku z wystarczającą liczbą obserwacji i lepsze dla co najmniej połowy z nich; czynnik, którego ablacja nie obniża AUC żadnego gatunku, zostaje ustawiony na neutralny (wszystkie wartości 1.0) przed wdrożeniem.

## 2. Dane (stan w `pipeline/data/bdl.duckdb`, 335 740 wydzieleń D-STAN)

| Pole | Tabela | Wartości (najczęstsze) | Puste |
|---|---|---|---|
| `moisture_cd` | `subarea` | `Ś`, `SŚ`, `WW`, `WSW`, `WO`, `ŁZ`, `BO`, `ŁN`, `BM`, `BSO`, `ŁP`, `SU`, `BBM` | ~1% |
| `degradation_cd` | `subarea` | `Z1`, `N2`, `N1`, `D1`, `D2`, `Z3`, `D3`, `Z2`, `P` | ~1% |
| `soil_subtype_cd` | `subarea` | `BRk`, `RDb`, `RDw`, `Bw`, `OGw`, `Bgw`, `Gw`, `RDbr`, `Bgms`, `BRb`, `MDbr`, `Gms`, `Pw` … | ~2% |
| `veg_cover_cd` | `subarea` | `ZAD`, `SZAD`, `SZCH`, `MSZC`, `ZIEL`, `ŚCIO`, `MSZ`, `NAGA` | ~1% |
| `damage_degree` | `subarea` | `0`–`100` (co 10) | ~59% |
| `density_cd` | `arod_storey` | zadrzewienie `0.4`–`1.0` (kody zwarcia `PEŁ`/`UM`/`PRZ`/`LUŹ` w danych nie występują) | ~60% wierszy |

Wydzielenia ze źródła API (Wieluń) nie mają tych pól → wszystkie nowe czynniki = 1.0.

## 3. Ingest

`STANDS_SQL` (`pipeline/ingest.py`) dostaje kolumny:

- z `subarea s`: `s.moisture_cd AS moist`, `s.degradation_cd AS degr`, `s.soil_subtype_cd AS soil`, `s.veg_cover_cd AS veg`, `TRY_CAST(s.damage_degree AS INTEGER) AS damage`;
- zadrzewienie piętra głównego: nowe CTE `dens` — `TRY_CAST(density_cd AS DOUBLE)` z `arod_storey` dla `storey_cd IN MAIN_STOREYS`, pierwszy wiersz wg `CASE storey_cd WHEN 'DRZEW' THEN 0 ELSE 1 END` (ta sama reguła co `dom`), kolumna `density`.

`load_stands` przenosi je do GeoDataFrame (kody: `strip()`, puste → `None`; liczby: `NaN` → `None`). Kody wilgotności, degradacji, gleby i runa normalizowane przez istniejące `_ascii_upper` (`Ś` → `S`, `Ł` → `L`), żeby klucze w `species.yaml` były ASCII jak kody drzew i siedlisk.

## 4. Model

### 4.1. Struktura

`Stand` dostaje pola z wartością domyślną `None`: `moist`, `degr`, `soil`, `veg`, `damage`, `density`. Istniejące konstrukcje `Stand(...)` (testy, legacy) działają bez zmian.

```
mod = Π czynnik_i(st, sp)                 # czynniki z §4.3
h   = partner_score × habitat_factor × max(MOD_FLOOR, mod)
MOD_FLOOR = 0.4
```

Czynniki są modyfikatorami, nie bramkami: nawet najgorsza kombinacja nie obniża `h` więcej niż do 40% wartości bez nich. Brak danych lub kod spoza tabeli → czynnik 1.0.

`habitat_components(st, sp)` (rejestr ze specu H §5) zwraca `partner`, `habitat`, oraz każdy czynnik z §4.3 osobno.

### 4.2. Konfiguracja w `species.yaml`

Nowa sekcja najwyższego poziomu `factors_default` z tabelami kod → mnożnik; gatunek może nadpisać całą tabelę danego czynnika w `factors:` (nadpisanie zastępuje tabelę, nie scala kluczy — prościej czytać). `forecast/species.py` parsuje to do `Species.factors: Mapping[str, Mapping[str, float]]` (tabele dyskretne) i `Species.factor_ramps` (czynniki liczbowe, §4.3). Nieznana nazwa czynnika lub mnożnik spoza [0, 1] → `ValueError` przy ładowaniu.

### 4.3. Czynniki i wartości startowe

Wartości startowe są eksperckie; stroi je raport ze specu H.

**`veg` — pokrywa runa** (`factors_default.veg`): `ZAD` 0.7, `ZIEL` 0.8, `SZAD` 0.9; pozostałe (`MSZ`, `MSZC`, `SZCH`, `SCIO`, `NAGA`) 1.0.

**`moist` — wilgotność siedliska** (`factors_default.moist`): `BO` 0.4, `BM` 0.4, `BBM` 0.4, `BSO` 0.6; pozostałe 1.0. Nadpisania:
- `kozlarz`: `BO` 0.8, `BM` 0.8, `BBM` 0.8, `BSO` 0.9;
- `maslak`, `kurka`: jak domyślne plus `WW` 0.85, `WSW` 0.85.

Uwaga: wilgotność częściowo jest już w kodzie TSL (np. `BMW`); dlatego mnożniki są łagodne i nie dotyczą `S`/`SS`.

**`degr` — degradacja** (`factors_default.degr`): `N1`, `N2` 1.0; `Z1`, `D1` 0.9; `Z2`, `Z3`, `D2`, `D3` 0.8; `P` 0.8. Nadpisanie dla `rydz` i `maslak`: tabela pusta (wszystko 1.0) — gatunki dobrze owocujące w zniekształconych borach sosnowych.

**`soil` — grupa gleby**: klucz tabeli = grupa = wiodące wielkie litery kodu (`BRk` → `BR`, `RDb` → `RD`, `Bgw` → `B`, `OGw` → `OG`, `MDbr` → `MD`, `Gms` → `G`, `Pw` → `P`). `factors_default.soil` pusta (1.0). Nadpisania:
- `kurka`, `podgrzybek`: `BR` 0.85, `G` 0.85, `OG` 0.85, `MD` 0.85;
- `kozlarz`: `B` 0.9, `RD` 0.9 (glejowe i murszowe 1.0);
- `borowik`: `G` 0.85, `OG` 0.85, `MD` 0.85.

**`damage` — uszkodzenie drzewostanu (%)**, rampa (`factors_default.damage: {full: 40, zero_at: 100, min: 0.6}`): ≤ 40 → 1.0, liniowo do 0.6 przy 100.

**`density` — zadrzewienie**, przedziały (`factors_default.density: [[0.4, 0.8], [0.9, 1.0], [1.0, 0.9]]` — lista `[górna granica włącznie, mnożnik]`, pierwszy pasujący): ≤ 0.4 → 0.8, ≤ 0.9 → 1.0, ≤ 1.0 → 0.9.

### 4.4. Wydajność `build_tiles`

`build_tiles` liczy `h` z cache po krotce atrybutów (`pipeline/build_tiles.py`, `cache[key]`). Klucz rozszerzamy o nowe pola; żeby cache dalej działał, `damage` jest w kluczu zaokrąglany do dziesiątek (dane i tak są co 10), a `density` do jednego miejsca po przecinku. Spodziewany wzrost liczby unikalnych kluczy: rząd wielkości; czas budowy sprawdzamy w planie i raportujemy.

## 5. Kontrakt danych

Bez zmian: kafelki mają te same atrybuty `h_<gatunek>` w skali 0–100, centroidy ten sam format wiersza, próg „max h ≥ 40” bez zmian. Zmienia się rozkład `h` (średnio w dół), co jest zgodne z §„Wersjonowanie” `docs/data/api.md` (znaczenie i skala pola te same). W `docs/data/api.md` dopisujemy jedno zdanie, że `h` uwzględnia też runo, wilgotność, glebę, degradację, uszkodzenia i zadrzewienie. `build.json` dostaje histogram `h` per gatunek (10 przedziałów) — pozwala porównać rozkład między buildami bez otwierania kafelków.

## 6. Testy

- `tests/test_habitat.py`: dla każdego czynnika — wartość z tabeli, kod nieznany → 1.0, `None` → 1.0; nadpisanie gatunkowe zastępuje tabelę; `MOD_FLOOR` (iloczyn 0.7 × 0.4 × 0.8 → 0.4); `Stand` bez nowych pól daje dotychczasowy wynik (regresja); grupa gleby z kodu (`BRk`→`BR`, `Bgw`→`B`, `OGw`→`OG`).
- `tests/test_species.py`: parsowanie `factors_default`/`factors`, `ValueError` dla nieznanego czynnika i wartości poza zakresem; aktualny `species.yaml` się ładuje.
- `tests/test_ingest.py`: fixture paczki z nowymi kolumnami → `load_stands` zwraca znormalizowane kody, `density` z piętra `DRZEW` przed `IP`.
- `tests/test_build_tiles.py`: klucz cache z zaokrągleniem `damage`.
