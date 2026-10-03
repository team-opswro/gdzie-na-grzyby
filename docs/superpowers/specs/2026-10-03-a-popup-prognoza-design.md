# A. Popup i prognoza — projekt

Data: 2026-10-03
Status: do przeglądu
Zakres: usprawnienia 1 (realne wartości pogody), 8 (wykres 7 dni), 10 (trend).
Powiązane: B (strzałka trendu w rankingu), D (wykres w trybie „Wszystkie gatunki”).
Kolejność wdrażania specyfikacji: **C → A → B → D** (C najpierw, bo dziś mapa może polecać rezerwaty);
każda jest samodzielna, zależności między nimi są miękkie (opisane w „Powiązane”).

## 1. Cel

Popup ma odpowiadać na pytania grzybiarza, a nie pokazywać składowe modelu:
„ile padało?”, „co psuje wynik?”, „który dzień w tygodniu najlepszy?”, „rośnie czy spada?”.

**Kryterium sukcesu:** po kliknięciu wydzielenia widać w jednym zdaniu, co ogranicza wynik,
sumę opadu w mm i temperaturę gleby w °C, wykres wyniku na 7 dni (klik w słupek zmienia dzień
na całej mapie) oraz strzałkę trendu.

## 2. Zmiany w `pogoda.json`

### 2.1. Dni
`days` ma **8** dat: `days[0]` = wczoraj, `days[1..7]` = dziś … +6. Wszystkie serie mają 8 elementów.
Frontend już filtruje przeszłe dni (`availableDays`), więc nawigacja dni się nie zmienia; wczoraj
służy wyłącznie do trendu dla dnia „dziś”. `forecast/run.py`: `DAYS = 7`, nowa stała `PAST_DAYS = 1`;
dni = `today + k` dla `k ∈ [-1, 6]`. Open-Meteo i tak zwraca 30 dni wstecz (`past_days=30`).

### 2.2. Realne wartości pogody — nowy klucz najwyższego poziomu `wx`
Wartości zależą od komórki, nie od gatunku, więc nie są powielane per gatunek:

```json
"wx": { "509_177": { "rain_mm": [8 liczb], "soil_t": [8 liczb], "soil_m": [8 liczb] } }
```

| pole | definicja (dla dnia o indeksie `i` w serii Open-Meteo) | zaokrąglenie |
|---|---|---|
| `rain_mm` | suma `precip[i-k]` dla `k ∈ RAIN_WINDOW` (5..21), bez wag; indeksy < 0 pomijane | 0,1 mm |
| `soil_t` | `_mean_back(soil_temp, i, TEMP_LOOKBACK)` (to samo, co liczy model), fallback `soil_temp[i]` | 0,1 °C |
| `soil_m` | `_mean_back(soil_moisture, i, MOISTURE_LOOKBACK)`, fallback `soil_moisture[i]` | 0,001 m³/m³ |

Funkcja `weather_values(s, i) -> WeatherValues` w `forecast/model.py` (obok `weather_multiplier`,
używa tych samych stałych).

### 2.3. Czynnik ograniczający — nowa seria `lim` per gatunek
`cells[cell][species].lim`: 8 wartości, każda to `"dry" | "dry_soil" | "cold" | "hot" | "season" | null`.

Reguła (`limiting_factor(comps, s, i, sp)` w `forecast/model.py`):
1. Kandydaci: składowe `season`, `temp`, `rain` o wartości `< LIM_THRESHOLD = 0.8`.
2. Brak kandydatów → `null`.
3. Wybierz składową o najmniejszej wartości; remis rozstrzyga kolejność `season`, `temp`, `rain`.
4. Mapowanie: `season` → `"season"`; `temp` → `"cold"`, gdy średnia temperatura gleby `< sp.temp[1]`,
   w przeciwnym razie `"hot"`; `rain` → `"dry_soil"`, gdy w `rain_factor` zadziałała kara za suchą
   glebę (`MOISTURE_PENALTY`), w przeciwnym razie `"dry"`.

`rain_factor` zwraca dodatkowo informację o zastosowaniu kary (np. wewnętrzna funkcja
`_rain_parts` zwracająca `(rain, penalized)`; publiczne `rain_factor` bez zmian sygnatury).

### 2.4. Schemat i rozmiar
`schema/pogoda.schema.json`: `days` i `series` mają `minItems = maxItems = 8`; nowy `$defs.lim`
(tablica 8 elementów `enum` + `null`); `species.required` += `lim`; nowy wymagany klucz `wx`
z `additionalProperties` → `{rain_mm, soil_t, soil_m}` (liczby, bez ograniczenia 0–1).
`rain_mm ≥ 0`, `soil_m ∈ [0, 1]`. Szacowany rozmiar: ~180 kB → ~260 kB (gzip: kilkadziesiąt kB).

## 3. Frontend

### 3.1. Zgodność ze starym plikiem
Wolumen `weather` może trzymać plik w starym formacie do najbliższego crona. `data.js`:
- `weatherFor(...)` zwraca dodatkowo `lim` (lub `null`, gdy brak pola) oraz `wx` dla komórki
  (`{rain_mm, soil_t, soil_m}` lub `null`, gdy brak klucza `wx`),
- brak `wx`/`lim` → popup pokazuje dotychczasowe procenty, bez zdania o ograniczeniu,
- trend dla dnia o indeksie 0 w `pogoda.days` → brak strzałki.

### 3.2. Popup (`popup.js`)
`renderPopup(props, ctx)` — sygnatura zmienia się na obiekt kontekstu
`{ pogoda, species, dayIdx, cell, onDaySelect }`, bo wykres potrzebuje całej serii.
Kolejność treści:
1. Nagłówek (ID; w B zastąpiony nazwami).
2. Wynik `xx/100 (klasa)` + strzałka trendu (3.4).
3. Zdanie o ograniczeniu, jeśli `lim != null`:
   `dry` „Ogranicza: za mało deszczu”, `dry_soil` „Ogranicza: przesuszona gleba”,
   `cold` „Ogranicza: za zimna gleba”, `hot` „Ogranicza: za ciepła gleba”, `season` „Ogranicza: poza sezonem”.
4. Wykres 7 dni (3.3).
5. Tabela: gatunek panujący, wiek, typ siedliskowy, siedlisko %, a jeśli jest `wx`:
   „Deszcz (5–21 dni wcześniej): 34,2 mm”, „Gleba: 11,3 °C, wilgotna”.
   Opis wilgotności: `soil_m < 0.15` „sucha”, `< 0.30` „umiarkowana”, wyżej „wilgotna”
   (stałe `SOIL_DRY = 0.15`, `SOIL_WET = 0.30` w `popup.js`; 0,15 = `soil_moisture_min` wszystkich gatunków).
6. `<details>` „Szczegóły modelu”: dotychczasowe procenty (opad, temperatura, sezon).

### 3.3. Wykres 7 dni
Nowy moduł `web/js/chart.js`:
- `chartData(pogoda, cell, species, h, todayIso)` → `[{date, idx, score, cls}]` dla dni dostępnych
  (`availableDays`), `score = round(h × w)` lub `null`; funkcja czysta, testowana w Node,
- `renderChart(data, selectedIdx, onSelect)` → element `<svg>` (inline, bez bibliotek):
  7 słupków, wysokość ∝ wynik (0–100), kolor `COLORS.classes[cls]`, brak danych = pusty kontur,
  wybrany dzień z obrysem, pod słupkiem skrót dnia tygodnia („pn”, „wt”…), nad słupkiem wartość.
  Każdy słupek to `<g role="button" tabindex="0" aria-label="sob. 4 paź: 72">`; klik/Enter → `onSelect(idx)`.

`ui.js`: `onDaySelect(idx)` ustawia `state.day` na pozycję `idx` w `days` i wywołuje `refresh()`;
po odświeżeniu popup otwiera się ponownie dla tego samego wydzielenia (zapamiętane `props` i `lngLat`).

### 3.4. Trend
`trend(pogoda, cell, species, h, dayIdx)` w `chart.js`:
- `prev` = wynik dla `dayIdx - 1` (także wczoraj z `days[0]`); brak → `dir = null`,
- `delta = score - prev`; `dir = "up"` gdy `delta ≥ 5`, `"down"` gdy `≤ -5`, inaczej `"flat"`,
- `peak` = dzień o najwyższym wyniku spośród dni **późniejszych** niż wybrany (tylko gdy jego wynik
  przewyższa bieżący o ≥ 5).
Prezentacja: ↑ / ↓ / → przy wyniku, `title` z opisem („+12 względem wczoraj”);
pod spodem „Szczyt: sob. (72)”, jeśli `peak`.

## 4. Testy

- pytest `tests/test_model.py`: `weather_values` (okno 5..21, krótsze serie), `limiting_factor`
  (null przy wszystkich ≥ 0,8; cold vs hot; dry vs dry_soil; remisy).
- pytest `tests/test_run.py`: 8 dni z wczoraj, obecność `wx` i `lim`, walidacja nowym schematem,
  błąd przy braku wczorajszego dnia w serii.
- `tests/fixtures/pogoda.json` aktualizowany do nowego formatu; dodatkowa fixture starego formatu
  dla testów zgodności JS.
- node `web/tests/chart.test.js`: `chartData` (dni przeszłe pominięte, brak danych), `trend`
  (progi ±5, brak poprzedniego dnia, peak), `weatherFor` na starym i nowym formacie.

## 5. Poza zakresem
Godzinowa prognoza, wykres składowych pogody, historia dłuższa niż 1 dzień.
