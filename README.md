# gdzie-na-grzyby

Hobbystyczna mapa szans na grzyby (borowik, podgrzybek, kurka, kozlarz, maślak, rydz) w lasach państwowych RDLP Katowice i RDLP Wrocław (72 nadleśnictwa z paczek BDL; kolejne regiony = dorzucenie paczek do `Nadlesnictwa/`).
Wynik = siedlisko (statyczne kafelki z danych BDL) × pogoda (prognoza Open-Meteo, odświeżana 2× dziennie).
Projekt: `docs/superpowers/specs/2026-10-03-grzyby-opolskie-design.md`, dane na R2: `docs/superpowers/specs/2026-10-03-e-dane-r2-design.md`.

## Testy

```sh
.venv/bin/pytest -v                 # Python (model, pipeline, forecast, healthcheck)
node --test web/tests/*.test.js     # JS (podaj pliki jawnie; katalog nie działa na Node 22)
```

## Przebudowa danych statycznych (pipeline)

Wykonywana lokalnie; wynik trafia do `pipeline/data/out/` (poza gitem): `lasy.pmtiles`,
`centroidy/index.json` + `centroidy/<lat0>_<lon0>.json` (kafelki 0,5°), `grid.json`, `nazwy.json`,
`gatunki.json`, `build.json`. Paczki BDL leżą w `Nadlesnictwa/` (poza gitem). Wygenerowane dane nie są
commitowane — strona w produkcji czyta je z bucketu R2 (kontrakt: `docs/data/api.md`).

```sh
python -m pipeline.ingest           # paczki BDL -> pipeline/data/bdl.duckdb + stands.parquet + nadlesnictwa.geojson
python -m pipeline.area             # obszar = obrysy nadleśnictw -> pipeline/data/obszar.geojson
python -m pipeline.fetch_reserves   # rezerwaty przyrody z GDOŚ (WFS) -> pipeline/data/rezerwaty.geojson
python -m pipeline.fetch_names      # nazwy nadleśnictw i leśnictw -> pipeline/data/out/nazwy.json
python -m pipeline.species_info     # gatunki.json (build robi to też sam)
podman build -f pipeline/Dockerfile -t grzyby-pipeline .      # tippecanoe (docker: to samo polecenie)
podman run --rm -v $PWD:/w:z -w /w grzyby-pipeline python -m pipeline.build   # -> pipeline/data/out/
python -m pipeline.publish --keep 3   # -> bucket: v/<build>/… + manifest.json (env S3_*)
```

`pipeline.build` wczytuje wszystkie wydzielenia naraz (~340 tys., kilka GB RAM).
`pipeline.publish --dry-run` pokazuje plan wysyłki bez danych dostępowych. Publikacja wysyła najpierw
pliki wersji, `manifest.json` na końcu, i usuwa wersje starsze niż 3 najnowsze (`--keep`).

## Uruchomienie lokalne (bez bucketu)

`docker-compose.local.yml` (samodzielny przykład) serwuje stronę na porcie 8080 i montuje
`pipeline/data/out/` jako `data/` (tryb lokalny: bez `DATA_BASE_URL` strona czyta `data/`, a bez
`manifest.json` — pliki wprost z tego katalogu):

```sh
docker compose -f docker-compose.local.yml up --build -d          # http://localhost:8080
# opcjonalnie prognoza (prawdziwe Open-Meteo, lokalny grid.json) -> pipeline/data/live/pogoda.json
docker compose -f docker-compose.local.yml --profile forecast run --rm forecast
docker compose -f docker-compose.local.yml down
```

Bez prognozy strona pokazuje baner „Brak danych pogodowych” i samą ocenę siedliska. Aby podejrzeć dane
z bucketu, ustaw `DATA_BASE_URL` (np. w `.env`) — wtedy montowane katalogi są ignorowane.
(Z Podmanem: `podman compose ...`; aby HEALTHCHECK działał, zbuduj w formacie docker:
`BUILDAH_FORMAT=docker podman compose ... up --build`; stan sprawdzisz `podman healthcheck run <kontener>`.)

**Serwowanie deweloperskie:** `python -m http.server` NIE obsługuje nagłówków Range, których wymaga PMTiles
(mapa się nie wczyta). Używaj stosu Compose albo serwera z obsługą Range.

## Wdrożenie z R2

Obraz `web` nie zawiera danych: bez `DATA_BASE_URL` strona szuka ich w `data/`, którego w obrazie nie ma
(w produkcji pokaże tylko podkład i baner braku danych). Kroki dla właściciela:

1. **Bucket:** w Cloudflare → R2 utwórz bucket (np. `gdzie-na-grzyby`).
2. **Publiczny odczyt:** w ustawieniach bucketu włącz publiczny dostęp przez `r2.dev` albo podłącz własną
   domenę (zalecane w produkcji: cache Cloudflare, brak limitów `r2.dev`). Ten adres to `DATA_BASE_URL`
   — zalecany z końcowym `/` (kod dopisze go, jeśli brak), np. `https://dane.example.pl/`.
3. **Token:** R2 → Manage API Tokens → token z uprawnieniem **Object Read & Write** ograniczonym do
   tego jednego bucketu. Zapisz Access Key ID, Secret Access Key i endpoint
   `https://<account_id>.r2.cloudflarestorage.com`.
4. **Publikacja danych** (lokalnie, po buildzie) — zmienne trzymaj poza repozytorium (np. plik
   `~/.config/gdzie-na-grzyby/r2.env` z `chmod 600`):

   ```sh
   set -a; . ~/.config/gdzie-na-grzyby/r2.env; set +a   # S3_ENDPOINT, S3_BUCKET, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY
   python -m pipeline.publish --keep 3
   ```

5. **CORS (raz):** strona czyta bucket z innej domeny, więc bucket potrzebuje reguły CORS
   (GET, HEAD, nagłówek `Range` dla PMTiles) dla każdego originu — dane są publiczne i tylko do odczytu.
   Token **Object Read & Write nie ma prawa** zmieniać konfiguracji bucketu (`PutBucketCors` →
   `AccessDenied`; `publish --cors` zgłasza to po wysłaniu danych, kod wyjścia 3). Ustaw regułę w panelu:
   R2 → bucket → **Settings → CORS Policy → Add/Edit**:

   ```json
   [
     {
       "AllowedOrigins": ["*"],
       "AllowedMethods": ["GET", "HEAD"],
       "AllowedHeaders": ["Range", "If-Match", "If-None-Match"],
       "ExposeHeaders": ["ETag", "Content-Range", "Content-Length"],
       "MaxAgeSeconds": 3600
     }
   ]
   ```

   (albo jednorazowo `publish --cors '*'` z tokenem **Admin Read & Write**). Kolejne publikacje — bez `--cors`.
6. **Coolify:** **New Resource -> Docker Compose** z repozytorium git, plik `docker-compose.yml`
   (porty nie są publikowane — routing robi Traefik w Coolify). Zmienne środowiskowe usług:
   - `web` — `DATA_BASE_URL`; ustaw domenę (port 80), HTTPS załatwia Coolify.
   - `forecast` — `DATA_BASE_URL` oraz `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`,
     `S3_SECRET_ACCESS_KEY` (`S3_REGION` domyślnie `auto`); bez domeny.
7. **Deploy.** `forecast` przy starcie pobiera `manifest.json` i `grid.json` z `DATA_BASE_URL`, liczy
   prognozę i wysyła `live/pogoda.json` do bucketu; potem cron o 05:00 i 14:00 (`Europe/Warsaw`).
   Healthcheck: ostatnie udane wysłanie młodsze niż 36 h (znacznik w `/state`, bez wolumenu — po
   restarcie kontener jest niezdrowy do pierwszego wysłania). Brak zmiennych → błąd w logu.
8. **Nowa wersja danych:** build + `pipeline.publish` — strona i `forecast` same przechodzą na nowy
   `manifest.json`; redeploy nie jest potrzebny.

Weryfikacja: `curl -sI <DATA_BASE_URL>manifest.json` (`content-encoding: gzip`, `cache-control: no-cache`)
i `curl -s -D - -o /dev/null -H 'Origin: https://example.org' -H 'Range: bytes=0-99' <DATA_BASE_URL>v/<build>/lasy.pmtiles`
→ `206` oraz `access-control-allow-origin` (brak tego nagłówka = brak reguły CORS, mapa się nie wczyta).

## Dane i licencje

- Siedliska: Bank Danych o Lasach (BDL), PGL Lasy Państwowe, stan 2026. Dane poglądowe, udostępniane w oparciu
  o regulamin BDL i ustawę o dostępie do informacji publicznej (szczegóły: `docs/data/bdl.md`).
- Pogoda: [Open-Meteo](https://open-meteo.com/) (darmowe API, użycie niekomercyjne).
- Rezerwaty: Generalna Dyrekcja Ochrony Środowiska (GDOŚ), WFS sdi.gdos.gov.pl.
- Podkłady: ortofotomapa i mapa topograficzna GUGiK (geoportal.gov.pl).
- Mapa podkładowa: © OpenStreetMap.
