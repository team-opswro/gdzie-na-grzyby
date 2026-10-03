# Grzyby Opolskie — projekt

Data: 2026-10-03
Status: do przeglądu

## 1. Cel i zakres

Hobbystyczna strona pokazująca na mapie szanse na grzyby w lasach województwa opolskiego, na wzór grzybnik.com i wysocki.lu/grzyby, w uproszczonej formie.

**Kryterium sukcesu:** użytkownik rano otwiera stronę na telefonie, wybiera gatunek i dzień (dziś … +6), widzi pokolorowane wydzielenia leśne oraz listę 10 najlepszych miejsc w promieniu 20 km od siebie. Utrzymanie sprowadza się do jednego codziennego zadania na VPS.

**W zakresie v1:**
- obszar: województwo opolskie oraz w całości (bez przycinania do granicy) dwa nadleśnictwa RDLP Wrocław przy Grodkowie: Henryków i Oława,
- 6 gatunków: borowik szlachetny, podgrzybek brunatny, kurka, koźlarz babka, maślak zwyczajny, rydz,
- model hybrydowy: stała ocena siedliska × dzienny mnożnik pogodowy,
- prognoza na 7 dni (dzień 0 = dziś),
- ranking top 10 w okolicy (GPS albo środek mapy),
- hosting na własnym VPS z Coolify.

**Poza zakresem v1:** konta użytkowników, płatności, zgłoszenia znalezisk, rozpoznawanie ze zdjęć, PWA i tryb offline, LiDAR i zwarcie koron, filtr „bez tłumów”, kalibracja modelu na danych z GBIF.

## 2. Architektura

Wariant „pliki statyczne + codzienny skrypt”. Na serwerze nie ma bazy danych ani API.

```
grzyby/
├── species.yaml         reguły gatunków — jedno źródło prawdy
├── pipeline/            Python, uruchamiany lokalnie raz na sezon
│   ├── Dockerfile       GDAL + tippecanoe
│   ├── fetch_bdl.py     pobranie danych BDL dla nadleśnictw z Opolskiego
│   ├── habitat.py       ocena siedliska 0–1 per (wydzielenie, gatunek)
│   ├── grid.py          siatka pogodowa 0,1°, przypisanie cell_id
│   └── build_tiles.py   → web/data/lasy.pmtiles, web/data/centroidy.json
├── forecast/            Python, uruchamiany codziennie w kontenerze
│   ├── Dockerfile       python:3.12-slim + supercronic
│   ├── weather.py       Open-Meteo: 30 dni wstecz + 7 dni prognozy
│   ├── model.py         mnożnik pogodowy 0–1 per (komórka, gatunek, dzień)
│   └── run.py           zapis pogoda.json (atomowo)
├── web/                 statyczny frontend
│   ├── index.html
│   ├── js/              data.js, map.js, ranking.js, popup.js, ui.js
│   ├── vendor/          maplibre-gl, pmtiles (lokalne kopie)
│   └── data/            lasy.pmtiles, centroidy.json, grid.json (commitowane)
├── schema/pogoda.schema.json   kontrakt danych Python ↔ JS
├── nginx.conf
└── docker-compose.yml
```

Przepływ danych:

```
BDL ──► pipeline (raz/sezon) ──► lasy.pmtiles, centroidy.json ──► repo ──► obraz web
Open-Meteo ──► forecast (2×/dzień) ──► pogoda.json ──► wolumen ──► web (nginx)
przeglądarka: wynik = h_<gatunek>(polygon) × w[cell][gatunek][dzień]
```

## 3. Dane wejściowe

**BDL (Bank Danych o Lasach)** — wydzielenia nadleśnictw, których zasięg obejmuje województwo opolskie (RDLP Katowice, Łódź), plus dwa nadleśnictwa dolnośląskie włączone w całości: Henryków (13-02) i Oława (13-20), warstwa `RDLP_Wroclaw_wydzielenia`. Wymagane minimum atrybutów na wydzielenie:

- geometria (polygon),
- adres leśny (identyfikator),
- gatunek panujący, opcjonalnie domieszki,
- wiek drzewostanu,
- typ siedliskowy lasu (opcjonalny, patrz §4.1, sytuacja awaryjna).

Wydzielenia nieleśne (zręby, bagna, drogi, grunty nieleśne) są odrzucane. Geometrie przycinane do obszaru = granica województwa (OSM) połączona z obrysami nadleśnictw `whole: true` (`pipeline/data/obszar.geojson`); Henryków i Oława nie są przycinane.

**Ryzyko nr 1:** format, licencja i zestaw atrybutów danych BDL nie zostały jeszcze potwierdzone. Pierwsze zadanie planu to ręczne sprawdzenie i pobranie próbki dla jednego nadleśnictwa.

**Open-Meteo Forecast API** — dla każdego punktu siatki: dobowe `precipitation_sum`, godzinowe `soil_temperature_6cm` i `soil_moisture_3_to_9cm`, `past_days=30`, `forecast_days=7`, strefa `Europe/Warsaw`. Zapytania wsadowe (wiele współrzędnych naraz).

**Siatka pogodowa:** regularna siatka 0,1° × 0,1° obejmująca województwo; zachowane tylko komórki przecinające się z lasem (~100). `cell_id` = `"<lat_idx>_<lon_idx>"`. Wydzielenie dostaje `cell` komórki, w której leży jego centroid. Siatka zapisywana do `web/data/grid.json` i używana przez `forecast/`.

## 4. Model

Wynik: `score = round(100 × h × w)`, zakres 0–100.

Wszystkie parametry gatunków są w `species.yaml`; kod nie zawiera liczb specyficznych dla gatunku.

### 4.1. Siedlisko `h` (offline)

`h = partner × wiek × typ_siedliska`, każdy czynnik 0–1.

- **partner:** 1,0, jeśli gatunek panujący jest partnerem gatunku grzyba; 0,6, jeśli partner występuje jako domieszka; 0 w pozostałych przypadkach.
- **wiek:** 0 poniżej `age_min`; liniowo od 0,3 do 1,0 między `age_min` a `age_opt`; 1,0 powyżej `age_opt`; jeśli zdefiniowano `age_max`, liniowy spadek do 0,3 w ciągu 20 lat po `age_max`.
- **typ_siedliska:** 1,0 dla typów preferowanych, 0,6 dla typów sąsiednich (zdefiniowanych jawnie w `species.yaml`), 0,2 dla pozostałych. Jeśli brak atrybutu typu siedliskowego, czynnik = 1,0 (model redukuje się do partner × wiek).

| Gatunek | Partnerzy | age_min / age_opt / age_max | Siedliska preferowane | Sezon |
|---|---|---|---|---|
| borowik szlachetny | świerk, sosna, buk, dąb | 30 / 50 / – | Bśw, BMśw, LMśw, Lśw | VII–X |
| podgrzybek brunatny | sosna, świerk | 20 / 30 / – | Bśw, BMśw, Bw, BMw | VIII–XI |
| kurka | sosna, świerk, buk, dąb | 20 / 30 / – | Bśw, BMśw, Bs | VI–X |
| koźlarz babka | brzoza | 10 / 15 / – | BMw, LMw, Bw | VI–X |
| maślak zwyczajny | sosna | 5 / 10 / 40 | Bśw, Bs | VIII–XI |
| rydz | sosna, świerk | 5 / 10 / 40 | LMśw, Lśw | VIII–X |

Wartość `h` zapisywana w kafelkach jako atrybut całkowity `h_<klucz_gatunku>` w skali 0–100.

### 4.2. Pogoda `w` (codziennie)

Dla komórki `c`, gatunku `s` i dnia `d ∈ {0..6}`: `w = opad × temperatura × sezon`.

- **opad:** `P = Σ waga(k) × opad(d−k)` dla `k = 5..21`; waga 1,0 dla `k = 7..14`, 0,5 dla pozostałych. `opad = clamp((P − 10) / (40 − 10), 0, 1)` (progi `rain_min`, `rain_full` per gatunek, domyślnie 10 i 40 mm). Kara ×0,5, jeśli średnia `soil_moisture_3_to_9cm` z dni d−3..d−1 < `soil_moisture_min` (domyślnie 0,15 m³/m³).
- **temperatura:** `T` = średnia `soil_temperature_6cm` z dni d−5..d−1. Funkcja trapezowa z parametrami `t_zero_low`, `t_opt_low`, `t_opt_high`, `t_zero_high` (np. borowik 6 / 12 / 20 / 26 °C).
- **sezon:** 1,0 w miesiącach sezonu; liniowe przejście do 0,1 w ciągu 14 dni przed początkiem i po końcu sezonu; 0,1 poza sezonem.

Dla dni prognozy dane „wsteczne” łączą historię z prognozą. Dni bez danych (brak w odpowiedzi API) traktowane jako opad 0, a temperatura z najbliższego dostępnego dnia.

### 4.3. Klasy kolorów

| wynik | klasa |
|---|---|
| < 10 | brak (szary, półprzezroczysty) |
| 10–25 | słabo |
| 25–45 | średnio |
| 45–65 | dobrze |
| > 65 | bardzo dobrze |

### 4.4. Zastrzeżenie

Model to heurystyki z literatury i wiedzy grzybiarskiej, bez kalibracji. Strona pokazuje to w stopce i w opisie metody.

## 5. Formaty danych

**`lasy.pmtiles`** — warstwa `lasy`, zoom 8–14, atrybuty: `id` (adres leśny), `cell`, `sp` (gatunek panujący), `age`, `hab` (typ siedliskowy lub pusty), `h_borowik`, `h_podgrzybek`, `h_kurka`, `h_kozlarz`, `h_maslak`, `h_rydz`.

**`centroidy.json`** — tylko wydzielenia z `max(h_*) ≥ 40`:
```json
{"species": ["borowik", "..."], "rows": [["<id>", lat, lon, "<cell>", h_borowik, "..."]]}
```

**`pogoda.json`** (zgodny z `schema/pogoda.schema.json`):
```json
{
  "generated_at": "2026-10-03T05:00:12+02:00",
  "days": ["2026-10-02", "...8 dat"],
  "wx": {"<cell_id>": {"rain_mm": [34.2, "...8"], "soil_t": [...], "soil_m": [...]}},
  "cells": {
    "<cell_id>": {
      "borowik": {"w": [0.82, "...8"], "rain": [...], "temp": [...], "season": [...], "lim": ["dry", null, "..."]}
    }
  }
}
```
Składowe `rain`/`temp`/`season` służą popupowi do wyjaśnienia wyniku.

Uwaga (zmiana formatu): `days` ma 8 dat — `days[0]` to wczoraj, `days[1..7]` to dziś … +6. Dodatkowo `wx` zawiera realne wartości pogody per komórka (opad z okna 5–21 dni, średnia temp. i wilgotność gleby), a `lim` per gatunek wskazuje czynnik ograniczający (`dry`, `dry_soil`, `cold`, `hot`, `season` lub `null`).

## 6. Frontend

Czysty HTML/CSS/JS (moduły ES), bez frameworka i bez kroku budowania. MapLibre GL + pmtiles.js, podkład OSM.

**Układ (najpierw telefon):** górny pasek z wyborem gatunku i dnia (◀ ▶), mapa na całej wysokości, przycisk „moja lokalizacja”, wysuwany dolny panel „Top 10 w promieniu 20 km”.

**Moduły:**
- `data.js` — ładuje `pogoda.json` i `centroidy.json`; `score(h, cell, species, day)`.
- `map.js` — źródło PMTiles; kolor wypełnienia z wyrażenia `h_<gatunek> × match(cell, …w…)`; zmiana gatunku lub dnia = `setPaintProperty`, bez ponownego pobierania kafelków.
- `ranking.js` — haversine, filtr promienia, sortowanie, top 10; klik → `flyTo` wydzielenia.
- `popup.js` — adres leśny, gatunek panujący, wiek, siedlisko, wynik i składowe (h, opad, temperatura, sezon).
- `ui.js` — kontrolki; stan (gatunek, dzień, pozycja mapy) w hashu URL.

**Sytuacje awaryjne:**
- `generated_at` starszy niż 36 h → żółty pasek „Prognoza nieaktualna (z dnia …)”.
- brak lub błąd `pogoda.json` → mapa samego siedliska (`h`) i komunikat „Brak danych pogodowych”.
- brak zgody na GPS → ranking od środka widoku mapy.
- dzień spoza zakresu `days` (stary plik) → selektor ogranicza się do dostępnych dni.

## 7. Wdrożenie (Coolify)

`docker-compose.yml` wdrażany przez Coolify z repozytorium git:

- **`web`** — `nginx:alpine`; obraz zawiera `web/` z danymi statycznymi; wolumen `weather` zamontowany tylko do odczytu pod `/usr/share/nginx/html/data/live/`.
- **`forecast`** — `python:3.12-slim` + supercronic; przy starcie jednorazowo uruchamia `run.py`, potem o 05:00 i 14:00 (`TZ=Europe/Warsaw`); zapis do wolumenu `weather`.

**nginx:** zapytania Range dla `.pmtiles`, gzip dla JSON, `Cache-Control: no-cache` dla `data/live/*`, długi cache dla `vendor/` i `data/*.pmtiles`.

**Odporność `forecast`:** 3 ponowienia z wykładniczym backoffem; zapis do pliku tymczasowego, walidacja schematu, potem `rename`; przy błędzie poprzedni `pogoda.json` zostaje. Healthcheck: plik młodszy niż 36 h.

**Dane statyczne:** `lasy.pmtiles` budowany lokalnie (`pipeline/Dockerfile`) i commitowany do `web/data/`; jeśli > 50 MB — Git LFS.

**HTTPS i domena:** konfiguracja w Coolify (Traefik), poza repozytorium.

## 8. Testy

- **pytest — `model.py`:** krzywe opadu, temperatury i sezonu (wartości brzegowe); scenariusze: susza → `w` < 0,1; 40 mm w oknie 7–14 dni + 15 °C w sezonie → `w` > 0,8; mróz → `w` = 0.
- **pytest — `habitat.py`:** syntetyczne wydzielenia: stary bór świeży sosnowy → wysokie `h` dla podgrzybka; ols olszowy → `h` ≈ 0 dla wszystkich; 15-letni sosnowy młodnik → wysokie `h` dla maślaka, niskie dla borowika.
- **pytest — `run.py`:** zamockowane Open-Meteo; poprawny plik zgodny ze schematem; przy błędzie API stary plik nienaruszony.
- **Kontrakt:** fixture `pogoda.json` walidowany schematem w teście Pythona i używany w testach JS.
- **node:test — frontend:** `score`, haversine, ranking (filtr promienia, sortowanie, remisy), wykrywanie nieaktualnej prognozy.
- **Smoke:** `docker compose up` lokalnie; strona się ładuje, `pogoda.json` powstaje, kafelki serwowane z Range.

## 9. Ryzyka

| Ryzyko | Skutek | Reakcja |
|---|---|---|
| BDL nie udostępnia potrzebnych atrybutów lub licencja zabrania | brak danych bazowych | sprawdzenie jako pierwsze zadanie; awaryjnie OSM `landuse=forest` + `leaf_type` (znacznie zgrubniej) |
| brak typu siedliskowego | słabsze `h` | model partner × wiek (§4.1) |
| limity Open-Meteo | brak prognozy | ~100 punktów × 2/dzień mieści się w darmowym limicie; zapytania wsadowe |
| heurystyki trafiają słabo | mała użyteczność | parametry w `species.yaml`, łatwe strojenie; kalibracja GBIF jako v2 |
