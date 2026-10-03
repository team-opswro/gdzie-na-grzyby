# G. Model pogody: bilans wodny, głębsza wilgotność, impuls temperatury, przymrozek — projekt

Data: 2026-10-03
Status: zaakceptowany (rozmowa 2026-10-03)
Zakres: rozszerzenie mnożnika pogodowego `w` w `forecast/model.py` i pobierania w `forecast/weather.py`; nowe pola w `live/pogoda.json` (wstecznie zgodne); tekst nowego czynnika ograniczającego w popupie.
Poza zakresem: zmiana formuły klienta `round(h × w)`, powiązanie pogody z terenem (spec I jest statyczny), zmiana siatki 0,1°.

## 1. Cel

Dziś `w = rain × temp × season`: opad ważony z okna 5–21 dni, kara za suchą glebę (3–9 cm), trapez temperatury gleby (6 cm), sezon. Model nie widzi parowania (30 mm w upale ≠ 30 mm we wrześniu), stanu głębszej gleby, typowego wyzwalacza owocnikowania (ochłodzenie po ciepłym okresie) ani przymrozku kończącego sezon.

**Kryterium sukcesu:** raport `pipeline.validate` (spec H) pokazuje AUC pogody nie gorsze niż linia bazowa dla każdego gatunku z wystarczającą liczbą obserwacji; kontener `forecast` publikuje `pogoda.json` zgodny z rozszerzonym schematem w czasie nie dłuższym niż 2× obecny przebieg; stara wersja strony działa z nowym plikiem.

## 2. Dane wejściowe (Open-Meteo)

`forecast/weather.py`, `PARAMS`:

```python
"daily": "precipitation_sum,et0_fao_evapotranspiration,temperature_2m_min",
"hourly": "soil_temperature_6cm,soil_moisture_3_to_9cm,soil_moisture_9_to_27cm",
```

`DailySeries` dostaje pola `et0: list[float]`, `t2m_min: list[float]`, `soil_moisture_deep: list[float]`; braki uzupełniane `_fill_nearest` jak dziś. Zmienne dzienne są tanie; trzecia zmienna godzinowa zwiększa „wagę” zapytania o ok. 50%. Plan wdrożenia mierzy wagę (nagłówki/odpowiedź 429) i w razie potrzeby zmniejsza `batch` w `fetch_series` z 50 do 30 oraz aktualizuje komentarz przy `RATE_LIMIT_WAIT_S`.

Te same zmienne są w Historical Forecast API, więc walidacja (spec H §4) liczy nowe składowe bez zmian w kodzie.

## 3. Model

Wszystkie nowe stałe globalne w `forecast/model.py` obok istniejących (`RAIN_WINDOW` itd.); parametry gatunkowe w `species.yaml` z wartością domyślną w `forecast/species.py` (jak `DEFAULT_RAIN_MIN`).

### 3.1. Bilans wodny (zmiana składowej `rain`)

W `_rain_parts` suma ważona opadu jest zastępowana bilansem w tym samym oknie i z tymi samymi wagami (`RAIN_CORE_WINDOW` = 1.0, krawędzie = 0.5):

```
water = Σ_k waga_k · precip[i-k]  −  ET_ALPHA · Σ_k waga_k · et0[i-k]
rain  = clamp((water − rain_min) / (rain_full − rain_min), 0, 1)
ET_ALPHA = 0.3
```

Progi `rain_min`/`rain_full` w `species.yaml` bez zmian; `ET_ALPHA` stroimy raportem H (kandydaci 0.0 / 0.15 / 0.3 / 0.5 — 0.0 odtwarza obecny model). Nazwa składowej zostaje `rain` (znaczenie w kontrakcie: „składowa wilgotności z opadu”, 0–1 — bez zmiany typu ani zakresu).

### 3.2. Głębsza wilgotność (kara za suchą glebę)

Kara `MOISTURE_PENALTY` działa, gdy średnia z `MOISTURE_LOOKBACK` (1–3 dni) z wilgotności efektywnej jest poniżej `soil_moisture_min`:

```
soil_m_eff = MOISTURE_SHALLOW_WEIGHT · soil_moisture + (1 − MOISTURE_SHALLOW_WEIGHT) · soil_moisture_deep
MOISTURE_SHALLOW_WEIGHT = 0.5
```

Przelotny deszcz zwilżający tylko wierzchnią warstwę nie znosi już kary w suszy; głęboka wilgoć po deszczowym okresie łagodzi karę po kilku suchych dniach.

### 3.3. Impuls temperaturowy (nowa składowa `pulse`)

```
drop  = mean(soil_temp[i-14 .. i-8]) − mean(soil_temp[i-5 .. i-1])
pulse = 1 + PULSE_MAX · clamp(drop / PULSE_DROP_FULL, 0, 1)
PULSE_MAX = 0.2, PULSE_DROP_FULL = 3.0  # °C
```

Brak danych za okno (początek serii) → `pulse = 1.0`. `pulse` ∈ [1.0, 1.2] — premia, nie kara, więc dotychczasowe wartości `w` pozostają punktem odniesienia.

### 3.4. Przymrozek (nowa składowa `frost`)

Parametr gatunkowy `frost_min` (°C, domyślnie −2.0; wszystkie obecne gatunki na domyślnej). Dla dnia `i` szukamy najbliższego dnia `j ≤ i` w ostatnich `FROST_RECOVERY_DAYS` dniach z `t2m_min[j] ≤ frost_min`:

```
frost = 1.0                                           # brak takiego dnia
frost = FROST_FLOOR + (1 − FROST_FLOOR) · (i − j) / FROST_RECOVERY_DAYS
FROST_FLOOR = 0.2, FROST_RECOVERY_DAYS = 7
```

Dzień przymrozku (`j = i`) → 0.2, po 7 dniach bez przymrozku → 1.0.

### 3.5. Złożenie

```
w = min(1.0, rain × temp × season × pulse × frost)
```

`WeatherComponents` dostaje pola `pulse` i `frost` (rejestr dla raportu H — spec H §5).

### 3.6. Czynnik ograniczający

`limiting_factor` rozważa także `frost` (kod `"frost"`); `pulse` nigdy nie ogranicza (≥ 1). Kolejność przy remisie: `season`, `frost`, `temp`, `rain`.

## 4. Kontrakt `pogoda.json`

Zmiany wstecznie zgodne (nowe pola, nowy kod enum) — `live/pogoda.json` bez nowego prefiksu, zgodnie z `docs/data/api.md` §„Wersjonowanie”.

- `cells[cell][gatunek]`: nowe tablice `pulse` (8 liczb, 1.0–1.2) i `frost` (8 liczb, 0–1).
- `lim`: nowy kod `"frost"`.
- `wx[cell]`: nowe tablice `et0_mm` (suma ET0 w oknie `RAIN_WINDOW`, mm, ≥ 0), `soil_m_deep` (średnia 9–27 cm z `MOISTURE_LOOKBACK`, m³/m³), `t2m_min` (minimum temperatury powietrza z ostatnich `FROST_RECOVERY_DAYS` dni, °C).
- `schema/pogoda.schema.json`: nowe pola **opcjonalne** w `species` i `wxcell` (nie w `required` — walidator akceptuje stary i nowy plik), `pulse` z własną definicją `series_pulse` (`minimum: 1`, `maximum: 1.2`), `lim` z `"frost"`.
- `docs/data/api.md`: opis nowych pól i kodu.

Zgodność klienta: `web/` ignoruje nieznane pola; stara wersja z nieznanym `lim` nie pokazuje tekstu (`LIM_TEXT[lim]` undefined → warunek w `web/js/popup.js` pomija). Nowa wersja dodaje:
- `LIM_TEXT.frost = "Ogranicza: niedawny przymrozek"`;
- w tabeli składowych popupu wiersze „Ochłodzenie” (`pulse` jako `+N%` względem 1.0) i „Przymrozek” (`frost` jako procent), wyświetlane tylko gdy pole jest w danych;
- w opisie wartości (`wx`) linię „Parowanie (5–21 dni): N mm”, gdy jest `et0_mm`.

## 5. Testy

- `tests/test_model.py`:
  - `ET_ALPHA = 0` → wynik identyczny jak przed zmianą (regresja na istniejących przypadkach);
  - bilans: wysokie ET0 obniża `rain` przy tym samym opadzie;
  - `soil_m_eff`: sucha płytka + mokra głęboka → brak kary przy wadze 0.5 i progu między wartościami;
  - `pulse`: spadek 0 → 1.0, spadek 3 °C → 1.2, spadek 6 °C → 1.2, wzrost → 1.0, za krótka seria → 1.0;
  - `frost`: dzień przymrozku 0.2, 7 dni później 1.0, liniowo pomiędzy, `frost_min` z gatunku;
  - `w` ograniczone do 1.0; `limiting_factor` zwraca `"frost"` i respektuje kolejność remisu.
- `tests/test_weather.py`: parsowanie nowych zmiennych z odpowiedzi fixture, uzupełnianie braków.
- `tests/test_run.py`: wynik waliduje się rozszerzonym schematem; plik bez nowych pól też się waliduje.
- `web/tests/popup.test.js`: tekst `frost`; wiersze `pulse`/`frost` tylko gdy obecne.
