# H. Walidacja modelu na obserwacjach — projekt

Data: 2026-10-03
Status: zaakceptowany (rozmowa 2026-10-03)
Zakres: offline'owy raport jakości modelu (`h` i `w`) na obserwacjach grzybów z GBIF; punkt odniesienia dla speców F (czynniki BDL), G (model pogody) i I (teren).
Poza zakresem: automatyczne dopasowanie wag, zbieranie obserwacji w aplikacji (wymaga backendu), publikacja raportu.

## 1. Cel

Wszystkie wagi i progi w `species.yaml` i `pipeline/habitat.py` są dziś eksperckie. Raport walidacji mówi, czy model odróżnia miejsca i dni ze znaleziskami od tła, i czy dana zmiana modelu (F, G, I) to poprawia.

**Kryterium sukcesu:** `python -m pipeline.validate` na danych z `pipeline/data/` generuje `pipeline/data/walidacja/walidacja.md` i `walidacja.json` z AUC siedliska i pogody per gatunek (lub „za mało danych”), AUC każdego czynnika osobno i ablacją; dwa przebiegi na tym samym cache dają identyczny wynik.

**Kolejność:** spec H wdrażany jako pierwszy; raport z obecnego modelu = linia bazowa, zapisywana jako `walidacja-baza.json` (kopia ręczna, poza gitem) i porównywana przez `--compare`.

## 2. Dane obserwacji (GBIF)

Moduł `pipeline/gbif.py`:

- **Takson:** `latin` z `content/gatunki.yaml` → `GET https://api.gbif.org/v1/species/match?name=<latin>&kingdom=Fungi` → `usageKey`. Brak dopasowania `EXACT`/`FUZZY` z `rank=SPECIES` → gatunek pominięty z ostrzeżeniem.
- **Obserwacje:** `GET /v1/occurrence/search` z `taxonKey`, `geometry` = WKT prostokąta otaczającego `pipeline/data/obszar.geojson`, `hasCoordinate=true`, `hasGeospatialIssue=false`, `basisOfRecord=HUMAN_OBSERVATION`, `occurrenceStatus=PRESENT`, `year=2000,<bieżący>`; paginacja `limit=300`, `offset` do wyczerpania (`endOfRecords`), twardy limit 100 000 rekordów.
- **Filtr po pobraniu:** `coordinateUncertaintyInMeters` ≤ 100 (brak wartości → odrzucone), `eventDate` z dokładnością do dnia (zakresy dat odrzucone), punkt wewnątrz `obszar.geojson`.
- **Tło (target-group):** to samo zapytanie z `kingdomKey=5` (wszystkie grzyby) zamiast `taxonKey` — obserwacje dowolnych grzybów, które odzwierciedlają, gdzie i kiedy ludzie w ogóle notują grzyby.
- **Cache:** surowe strony odpowiedzi w `pipeline/data/raw/gbif/<klucz>/<offset>.json`; ponowny przebieg nie odpytuje API, chyba że `--refresh`. Pobieranie: timeout 30 s, 3 ponowienia z backoffem, pauza 0,2 s między stronami.
- Wynik: DataFrame `species, gbif_id, lat, lon, date`.

## 3. Walidacja siedliska

1. **Złączenie:** obserwacje (EPSG:4326) ↔ wydzielenia z `load_stands` (`pipeline/ingest.py`) przez `geopandas.sjoin(predicate="within")`. Raport podaje liczbę obserwacji poza wydzieleniami (pominięte).
2. **Obecności:** unikalne wydzielenia z ≥ 1 obserwacją gatunku.
3. **Tło:** unikalne wydzielenia z ≥ 1 obserwacją dowolnego grzyba (§2), bez obecności danego gatunku. Gdy tło > 20 × obecności — losowa próba 20 × obecności (`seed=0`).
4. **Metryki per gatunek:**
   - AUC (Mann–Whitney, remisy liczone jako ½) dla `h` — tej samej funkcji `habitat_score`, której używa `build_tiles`;
   - AUC każdego czynnika osobno: `partner_score`, `habitat_factor`, `age_factor` panującego oraz czynników dodanych w F i I (rejestr czynników, §5);
   - ablacja: AUC `h` z danym czynnikiem zastąpionym przez 1.0;
   - lift: odsetek obecności wśród wydzieleń z `h ≥ 60` podzielony przez odsetek obecności w całej próbie.
5. Gatunek z < 30 obecnościami → w raporcie „za mało danych (n=…)”, bez metryk.

## 4. Walidacja pogody

- **Zakres:** obserwacje od 2022-01-01 (od tej daty dostępne jest Open-Meteo Historical Forecast API ze zmiennymi identycznymi jak prognoza: `soil_temperature_6cm`, `soil_moisture_3_to_9cm` i zmienne z G).
- **Dane:** `https://historical-forecast-api.open-meteo.com/v1/forecast` dla środka komórki siatki 0,1° (`pipeline/grid.py`: `cell_id`), jeden zakres dat na komórkę i rok: od 1 maja − 21 dni do 30 listopada. Parsowanie przez `forecast.weather.daily_from_response` (ten sam kształt odpowiedzi). Cache w `pipeline/data/raw/meteo/<cell>_<rok>.json`.
- **Obecności:** (komórka, dzień) z obserwacją gatunku. **Tło:** dla każdej obecności 5 losowych dni (`seed=0`) z tej samej komórki i roku, w oknie sezonu gatunku ± 14 dni, bez dni z obserwacją gatunku.
- **Metryki per gatunek:** AUC dla `w` oraz dla każdej składowej (`rain`, `temp`, `season`, a po G także `pulse`, `frost`), liczonych funkcjami z `forecast/model.py` na serii `DailySeries`.
- Limity Open-Meteo: zapytania sekwencyjnie, pauza 1 s; na 429 — ten sam mechanizm co `forecast/weather.py` (`RATE_LIMIT_WAIT_S`).

## 5. Rejestr czynników

Żeby raport sam obejmował czynniki dodawane w F i I, `pipeline/habitat.py` udostępnia `habitat_components(st, sp) -> dict[str, float]` (nazwa czynnika → wartość), a `habitat_score(st, sp, neutral=frozenset())` liczy wynik z regułami modułu (np. dolne ograniczenie modyfikatorów ze specu F), traktując czynniki z `neutral` jako 1.0 — tak liczona jest ablacja. Analogicznie `forecast.model.weather_multiplier` zwraca `WeatherComponents`, których pola poza `w` raport iteruje (`dataclasses.fields`). Raport nie zna czynników z nazwy.

## 6. CLI i wynik

```sh
python -m pipeline.validate [--species borowik,kurka] [--refresh] [--no-weather] \
       [--compare walidacja-baza.json]
```

- `walidacja.json`: `{"generated_at", "build", "species": {<key>: {"n_presence", "n_background", "habitat": {"auc", "lift60", "factors": {<name>: {"auc", "ablation_auc"}}}, "weather": {"n", "auc", "components": {<name>: auc}}}}}`; `build` z `pipeline/data/out/build.json`, jeśli istnieje.
- `walidacja.md`: tabela per gatunek; przy `--compare` dodatkowa kolumna Δ AUC względem pliku bazowego.
- Pliki w `pipeline/data/walidacja/` (dopisany do `.gitignore`). **Nie** w `pipeline/data/out/`: `publish.upload_plan` wysyła wszystkie pliki z katalogu builda (`rglob`) i odrzuca inne rozszerzenia niż `.json`/`.pmtiles`, więc raport tam zablokowałby publikację albo wyciekłby do bucketu.

## 7. Testy

- `tests/test_gbif.py`: paginacja i filtry na odpowiedziach z `responses` (fixture z 2 stronami), cache — drugi przebieg bez żądań HTTP.
- `tests/test_validate.py`: `auc` (znane przypadki: idealne rozdzielenie = 1.0, odwrócone = 0.0, remisy = 0.5), losowanie tła deterministyczne, złączenie punkt-poligon na małym GeoDataFrame, „za mało danych” poniżej 30, struktura `walidacja.json`.
- Brak testów sieciowych.

## 8. Ryzyka

- Obserwacji grzybów z GBIF dla dwóch RDLP może być mało (dziesiątki na gatunek). Raport to pokaże; w razie potrzeby można później poszerzyć źródła (np. iNaturalist bezpośrednio) — poza zakresem.
- Obserwacje mają bias drogowy/miejski; target-group background go łagodzi, ale nie usuwa — AUC interpretujemy porównawczo (przed/po zmianie), nie absolutnie.
