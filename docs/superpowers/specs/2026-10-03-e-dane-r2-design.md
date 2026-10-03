# E. Dane dla całego kraju na R2 — projekt

Data: 2026-10-03
Status: zaakceptowany (rozmowa 2026-10-03)
Zakres: baza danych w pipeline (DuckDB), domieszki z opisów taksacyjnych BDL, obszar = 72 nadleśnictwa z paczek + Wieluń, centroidy w kafelkach, publikacja danych i prognozy na Cloudflare R2 jako „statyczne API” (kontrakt także dla przyszłej aplikacji mobilnej).
Poza zakresem: płatności, konta, reklamy, aplikacja mobilna, cały kraj (pipeline ma go umożliwiać — kolejne RDLP to dorzucenie paczek).

## 1. Cel

Pipeline skaluje się do całej Polski (ok. 2–2,5 mln wydzieleń), a strona i przyszła aplikacja czytają te same wersjonowane pliki z R2. Ocena siedliska uwzględnia domieszki z opisów taksacyjnych.

**Kryterium sukcesu:** `pipeline.ingest` + `pipeline.build` + `pipeline.publish` budują i publikują wersję danych dla 73 nadleśnictw; strona z `DATA_BASE_URL` wskazującym na bucket (lokalnie MinIO) pokazuje mapę, ranking (z kafelków centroidów) i prognozę wysłaną przez kontener `forecast` do bucketu; w repozytorium nie ma już wygenerowanych danych.

## 2. Dane wejściowe

### 2.1. Paczki BDL (`Nadlesnictwa/`, poza gitem)
Pliki `BDL_<RR>_<NN>_<NAZWA>_<ROK>[.zip]` (zip lub rozpakowany katalog). 72 unikalne nadleśnictwa (RDLP Katowice 02, Wrocław 13). Duplikaty z sufiksem `(1)`: wybierany plik z najpóźniejszą „Data wytworzenia danych” z `metadane.txt`; przy remisie — bez sufiksu. Pliki tekstowe: UTF-8, separator TAB, nagłówek w pierwszym wierszu, wartości z dopełnieniem spacjami (trim).

Używane tabele:
- `f_subarea.txt` — `arodes_int_num`, `area_type_cd`, `site_type_cd`, `forest_func_cd`, `sub_area`, (oraz zachowywane do przyszłego użytku: `moisture_cd`, `soil_subtype_cd`, `veg_cover_cd`, `plant_comm_cd`, `stand_struct_cd`, `silviculture_cd`, `rotation_age`).
- `f_storey_species.txt` — `arodes_int_num`, `storey_cd`, `sp_rank_order_act`, `species_cd`, `species_age`, `part_cd_act`, `height`, `bhd`.
- `f_arod_storey.txt` — `arodes_int_num`, `storey_cd`, `st_rank_order_act`, `density_cd` (zachowywane, nieużywane w modelu).
- `G_SUBAREA.shp` — geometria i `a_i_num`, `adr_for` (adres leśny); złączenie `a_i_num = arodes_int_num`.
- `G_INSPECTORATE.shp` — obrys nadleśnictwa (do obszaru).

### 2.2. Nadleśnictwa bez paczki
Wieluń (`06-20`) — jak dziś z OGC API (`fetch_bdl`), bez domieszek; obrys z kolekcji `nadlesnictwa`. Konfiguracja: `pipeline/bdl_fields.yaml` → lista `districts` zastąpiona przez `api_districts` (tylko nadleśnictwa bez paczki); nadleśnictwa z paczek są wykrywane automatycznie z katalogu.

### 2.3. Inne źródła (bez zmian)
Rezerwaty GDOŚ (`fetch_reserves`, obszar = nowy obszar), nazwy leśnictw (`fetch_names` — dla wszystkich nadleśnictw; nazwy nadleśnictw z paczek: `G_INSPECTORATE`/`metadane.txt`), treści gatunków (`species_info`).

## 3. Baza (DuckDB)

`pipeline/data/bdl.duckdb` (poza gitem), budowana przez `python -m pipeline.ingest [--packages Nadlesnictwa]` od zera przy każdym uruchomieniu (idempotentnie). Tabele: `district(prefix, name, source, produced_at)`, `subarea`, `storey_species`, `arod_storey` (kolumny jak w §2.1 + `prefix`), geometrie w `pipeline/data/stands.parquet` (GeoParquet: `a_i_num`, `id` = znormalizowany `adr_for`, `prefix`, `geometry` EPSG:4326). Wieluń z API trafia do tych samych struktur (`source = 'api'`, `storey_species` puste, `subarea` z pól API).

Widok/zapytanie `stands` (wynik w Pythonie, kolumny jak dziś w `load_bdl` + nowe): `id`, `sp_main`, `age`, `hab`, `fun`, `partners` (lista `(species, share_code, age)` z pięter `DRZEW`, `IP`, `IIP` poza gatunkiem panującym), `geometry`. Gatunek panujący = `sp_rank_order_act = 1` w pierwszym piętrze (`DRZEW` lub `IP`); dla źródła API — `species_cd`/`spec_age` jak dziś. Filtr lasu jak dziś: `area_type = 'D-STAN'` i niepusty gatunek panujący.

DuckDB jest jedynym miejscem złączeń atrybutów; geometrie przetwarza geopandas (jak dziś).

## 4. Model — domieszki i nowe kody siedlisk

### 4.1. Partner
`partner_factor` zastępuje stałe `ADMIXTURE_FACTOR`: ocena partnera = max po kandydatach:
- gatunek panujący należący do `partners` gatunku grzyba → `1.0 × age_factor(wiek panującego)`,
- każda domieszka należąca do `partners` → `SHARE_WEIGHT[udział] × age_factor(wiek domieszki)` (brak wieku → `AGE_UNKNOWN_FACTOR`).

`SHARE_WEIGHT`: `PJD` 0.2, `MJS` 0.3, `1` 0.5, `2` 0.7, `3` 0.7, `4`–`10` 0.9; nieznany/pusty kod → 0.3.

Ocena siedliska = ocena partnera × `habitat_factor` (wiek jest już w ocenie partnera; dotychczasowe mnożenie przez `age_factor` panującego znika z `habitat_score`). Dla źródła API (brak domieszek) wynik jest identyczny jak dziś.

### 4.2. Nowe kody siedlisk (odpowiedniki)
W `species.yaml` każdy kod dopisany obok odpowiednika w tych samych listach: `LMWYZSW ≙ LMWYZ`, `LWYZSW ≙ LWYZS`, `BMWYZSW ≙ BMWYZ`, `BMWYZW ≙ BMW`, `LMGW ≙ LMW`, `BMGW ≙ BMW`, `BWG ≙ BW`, `BMGB ≙ BMB`, `BGB ≙ BB`, `LMG ≙ LMGSW`, `LWYZ ≙ LWYZS`, `LG ≙ LGSW`. Bez odpowiednika (łęgi, olsy, mieszane bagienne liściaste — „inne siedlisko”): `LL`, `LLWYZ`, `LLG`, `OL`, `OLJ`, `OLJWYZ`, `OLJG`, `OLG`, `LMB`. Każdy nowy kod dostaje nazwę w `content/gatunki.yaml` (`codes.habitats`). Lista w `docs/data/bdl.md`.

## 5. Obszar, siatka, kafelki

- Obszar = suma obrysów wszystkich nadleśnictw (paczki: `G_INSPECTORATE`; API: kolekcja `nadlesnictwa`), uproszczona do 100 m; bez przycinania do województw. `pipeline/data/obszar.geojson` generowany przez `ingest`.
- Siatka pogodowa 0,1° jak dziś (komórki z centroidów lasu).
- `lasy.pmtiles` jak dziś (warstwy `lasy`, `rezerwaty`).

## 6. Centroidy w kafelkach

`centroidy/index.json`: `{ "tile": 0.5, "species": [...], "tiles": ["<lat0>_<lon0>", ...] }`; `centroidy/<lat0>_<lon0>.json`: `{ "rows": [[id, lat, lon, cell, h_...], ...] }` (wiersze jak dziś, bez `species` w każdym pliku), gdzie `lat0 = floor(lat/0.5)*0.5`, `lon0 = floor(lon/0.5)*0.5`, zapis z jedną cyfrą po przecinku (`50.5_17.0`). Rezerwaty wykluczone jak dziś, próg `CENTROID_THRESHOLD` bez zmian.

Frontend: `loadCentroidTiles(origin, radiusKm)` pobiera kafelki z bboxu promienia (tylko obecne w `tiles`), cache w pamięci; ranking łączy wiersze pobranych kafelków i działa jak dziś. Ładowanie `w=` (spec B) szuka wydzielenia w kafelku zawierającym środek z hasha, a gdy go nie ma — w sąsiednich (3×3).

## 7. Publikacja na R2

### 7.1. Układ bucketu
- `v/<build>/lasy.pmtiles`, `v/<build>/centroidy/…`, `v/<build>/grid.json`, `v/<build>/nazwy.json`, `v/<build>/gatunki.json` — niezmienne, `Cache-Control: public, max-age=31536000, immutable`. `<build>` = `YYYYMMDD-HHMM` (UTC) + `-` + 7 znaków hash git.
- `manifest.json` — `{ "build": "<build>", "base": "v/<build>/", "generated_at": "...", "files": {"lasy": "lasy.pmtiles", ...} }`, `Cache-Control: no-cache`.
- `live/pogoda.json` — `Cache-Control: no-cache`.
- Content-Type: `application/json`, `application/octet-stream` (pmtiles).

### 7.2. `python -m pipeline.publish`
Wysyła katalog wyjściowy builda do `v/<build>/`, potem `manifest.json` (ostatni — atomowe przełączenie wersji). Opcja `--keep 3` usuwa starsze wersje poza 3 najnowszymi. `--cors <origin,...>` ustawia CORS bucketu: `GET`, `HEAD`, nagłówki `Range`, `If-Match`, `If-None-Match`, eksponowane `ETag`, `Content-Range`, `Content-Length`. Konfiguracja z env: `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_REGION` (domyślnie `auto`). Biblioteka: `boto3`.

### 7.3. Prognoza
Kontener `forecast` przy każdym przebiegu: pobiera `manifest.json` i `grid.json` z publicznego `DATA_BASE_URL`, liczy `pogoda.json` (format A bez zmian), waliduje, wysyła do `live/pogoda.json` (env jak w §7.2) i zapisuje lokalny znacznik czasu udanego wysłania. Healthcheck: znacznik młodszy niż 36 h. Brak danych dostępowych → błąd w logu i niezdrowy kontener (bez zapisu lokalnego jako obejścia). Wolumen `weather` i jego montowanie w `web` znikają.

### 7.4. Frontend
`web/config.json` generowany przy starcie kontenera `web` z env `DATA_BASE_URL` (np. `https://data.example.pl/`); brak zmiennej → `"data/"` (tryb lokalny bez R2). `loadData` czyta `config.json` → `manifest.json` → pliki z `base`; `pogoda.json` z `live/`. PMTiles z pełnego URL (Range przez CORS).

### 7.5. Kontrakt
`docs/data/api.md` — opis wszystkich plików (ścieżki, formaty, nagłówki cache, wersjonowanie, zgodność wstecz: nowe pola dopisywane, istniejące nie zmieniają znaczenia; zmiana niekompatybilna = nowy prefiks `v2/`).

## 8. Repozytorium i środowisko lokalne

- Z gita usuwane: `web/data/lasy.pmtiles`, `web/data/centroidy.json`, `web/data/grid.json` (generowane). `web/data/nazwy.json`, `gatunki.json` też stają się wynikiem builda (źródła zostają: `content/`, `species.yaml`, `pipeline/data/rezerwaty.geojson`, `obszar.geojson`).
- `.gitignore`: `Nadlesnictwa/`, `pipeline/data/*.duckdb`, `pipeline/data/*.parquet`, `pipeline/data/out/`.
- `docker-compose.local.yml` (commitowany przykład) z MinIO (bucket tworzony przy starcie, publiczny odczyt) i `DATA_BASE_URL` wskazującym na MinIO; README: pełna ścieżka „ingest → build → publish → compose up”.
- Wynik builda: `pipeline/data/out/` (dotychczasowe `web/data`).

## 9. Wdrożenie

Gałąź `feat/dane-r2`. Merge do `main` dopiero gdy: bucket R2 istnieje, dane opublikowane, w Coolify ustawione `DATA_BASE_URL` (web) i dane dostępowe (forecast). README sekcja „Wdrożenie z R2” z listą kroków dla właściciela (bucket, token z uprawnieniem Object Read & Write tylko do bucketu, publiczna domena, CORS przez `publish --cors`).

## 10. Testy

- pytest: ingest (zip i katalog, duplikaty `(1)`, trim, filtr lasu, złączenie z geometrią, partnerzy z właściwych pięter), model (`SHARE_WEIGHT`, wiek domieszki, max po kandydatach, zgodność wyniku dla danych bez domieszek), kafelki centroidów (klucze, wykluczenie rezerwatów, index), publish (moto lub stub S3: kolejność manifest-ostatni, nagłówki, `--keep`), forecast upload (stub), nowe kody siedlisk (pary odpowiedników).
- node: `loadCentroidTiles` (wybór kafelków po bboxie, cache, brak kafelka), `loadData` z manifestem i `config.json`, fallback `data/`.
- e2e: MinIO + compose + Playwright: mapa, ranking, popup, prognoza z bucketu, Range dla PMTiles przez CORS.

## 11. Ryzyka
- Rozmiar `lasy.pmtiles` dla 73 nadleśnictw ~100–200 MB — R2 bez opłat za transfer; tippecanoe `--drop-smallest-as-needed` jak dziś.
- Zmiana `habitat_score` (wiek z partnera) zmienia wyniki także tam, gdzie panujący nie jest partnerem, a domieszka jest — to zamierzone.
- Warunki BDL: obowiązek poinformowania BDL o przetworzeniu (e-mail właściciela, poza kodem).
