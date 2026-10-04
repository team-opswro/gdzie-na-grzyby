# gdzie-na-grzyby

Hobbystyczna mapa szans na grzyby (borowik, podgrzybek, kurka, kozlarz, maślak, rydz) w lasach państwowych RDLP Katowice i RDLP Wrocław (72 nadleśnictwa z paczek BDL; kolejne regiony = dorzucenie paczek do `Nadlesnictwa/`).
Wynik = siedlisko (statyczne kafelki z danych BDL) × pogoda (prognoza Open-Meteo, odświeżana 2× dziennie).
Projekt: `docs/superpowers/specs/2026-10-03-grzyby-opolskie-design.md`, dane na R2: `docs/superpowers/specs/2026-10-03-e-dane-r2-design.md`.

## Testy

```sh
.venv/bin/pytest -v                 # Python (model, pipeline, forecast, healthcheck)
node --test web/tests/*.test.js     # JS (podaj pliki jawnie; katalog nie działa na Node 22)
```

## Wrocław, Miękinia, Milicz i Twardogóra

Mapa bez parametrów w adresie startuje na Wrocławiu. Lista **Okolica** pozwala przejść
do Miękini, Obornik Śląskich, Oleśnicy Śląskiej, Oławy, Milicza, Twardogóry lub Opola;
wybór przenosi także ranking i wyłącza wcześniejszy punkt GPS. Udostępniony link
z parametrem `c=` nadal otwiera wskazane miejsce — także po nowym wdrożeniu.

Te okolice są obecne w zweryfikowanym zbiorze produkcyjnym
`20261004-1408-12d72c4`. Zmiana widoku wymaga wdrożenia obrazu `web`, bez ponownego
publikowania danych. Rozpoznanie i wyniki kontroli: [docs/data/wroclaw.md](docs/data/wroclaw.md).
Nowe wejście bez parametrów wybiera **Samochodem → 50 km**. Otwórz panel rankingu
i kliknij **Oblicz dojazd**. Punktem wyjazdu jest środek mapy lub GPS; **Start z mapy**
ustawia nowy punkt. Po obliczeniu start jest zachowany podczas oglądania miejsc na mapie.
Linki sprzed tej zmiany zachowują ranking w linii prostej; sposób liczenia można przełączyć.

Ranking samochodowy sprawdza dojazd do parkingów z istniejących PMTiles, w odległości
do 1,5 km od punktu w lesie (w linii prostej). Długość najszybszej trasy i orientacyjny
czas pochodzą z OSRM/FOSSGIS; limit dotyczy jazdy w jedną stronę, bez uwzględniania korków.
Sprawdzane są maksymalnie 200 najwyżej ocenionych oddziałów i po trzy najbliższe parkingi.
Jeżeli nie znaleziono dziesięciu propozycji w tym zakresie, aplikacja informuje o ograniczeniu.
Obliczenie dojazdu wysyła współrzędne startu i parkingów do usługi routingu po kliknięciu
przycisku. Brak potwierdzonej trasy powoduje pominięcie propozycji; awaria pokazuje błąd.

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

5. **Jak strona czyta bucket — proxy (domyślnie) albo wprost:**
   - **Proxy (domyślny tryb przy `DATA_BASE_URL`):** kontener `web` przy starcie generuje w nginx
     lokalizację `/dane/`, która przekazuje żądania do `DATA_BASE_URL` (także `Range` dla PMTiles → `206`,
     `ETag`/`If-None-Match`, `Content-Encoding: gzip` i `Cache-Control` z bucketu bez zmian; tylko `GET`/`HEAD`),
     a `config.json` dostaje `"dataBase": "/dane/"`. Przeglądarka czyta dane z tej samej domeny co strona,
     więc **bucket nie potrzebuje reguły CORS**. `DATA_BASE_URL` musi mieć postać `https://host[/ścieżka/]`
     (znaki `A-Z a-z 0-9 . _ ~ / -`) — inaczej kontener nie wystartuje (czytelny błąd w logu).
     Koszt: cały ruch danych (≈110 MB PMTiles na wersję, czytane fragmentami) idzie przez VPS, a `r2.dev`
     ma limit żądań i brak cache Cloudflare — w produkcji podłącz do bucketu własną domenę (punkt 9).
     nginx rozwiązuje nazwę hosta przy żądaniach (resolver z `/etc/resolv.conf`, cache 5 min), więc start
     kontenera nie zależy od DNS, a zmiana adresów IP bucketu nie wymaga restartu. Duże odpowiedzi bez
     `Range` są strumieniowane (bez buforowania na dysku VPS).
   - **Wprost (`DATA_DIRECT=1`):** `config.json` dostaje sam `DATA_BASE_URL`, przeglądarka czyta bucket
     bezpośrednio (bez obciążania VPS). `DATA_BASE_URL` musi zaczynać się od `https://` (inaczej kontener
     nie wystartuje — strona HTTPS nie może czytać danych po HTTP). Wymaga reguły CORS na buckecie (GET, HEAD, nagłówek `Range`).
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

     (albo jednorazowo `publish --cors '*'` z tokenem **Admin Read & Write**), a potem ustaw w `web`
     `DATA_DIRECT=1`. Aplikacje natywne CORS nie potrzebują — czytają bucket wprost w obu trybach.
6. **Coolify:** **New Resource -> Docker Compose** z repozytorium git, plik `docker-compose.yml`
   (porty nie są publikowane — routing robi Traefik w Coolify). Zmienne środowiskowe usług:
   - `web` — `DATA_BASE_URL` (opcjonalnie `DATA_DIRECT=1`, patrz punkt 5); ustaw domenę (port 80),
     HTTPS załatwia Coolify.
   - `forecast` — `DATA_BASE_URL` oraz `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`,
     `S3_SECRET_ACCESS_KEY` (`S3_REGION` domyślnie `auto`); bez domeny.
7. **Deploy.** `forecast` przy starcie pobiera `manifest.json` i `grid.json` z `DATA_BASE_URL`, liczy
   prognozę i wysyła `live/pogoda.json` do bucketu; potem cron o 05:00 i 14:00 (`Europe/Warsaw`).
   Healthcheck: ostatnie udane wysłanie młodsze niż 36 h (znacznik w `/state`, bez wolumenu — po
   restarcie kontener jest niezdrowy do pierwszego wysłania; `start-period` 15 min obejmuje pierwszy przebieg
   z oczekiwaniem na limit Open-Meteo). Brak zmiennych → błąd w logu.
   **Limity Open-Meteo:** darmowe API ma limity minutowe, godzinowe i dzienne (liczone w „wywołaniach”;
   jeden przebieg dla całego gridu to ~14 partii po ~130, czyli ~1800). Na `429` `forecast` czeka ~minutę (do 6 razy);
   jeśli limit nadal obowiązuje, przerywa cały przebieg (błąd w logu: `przerwano: Open-Meteo: limit żądań
   (429)…`), a `live/pogoda.json` zostaje bez zmian do następnego uruchomienia z crona. Każdy redeploy /
   restart `forecast` robi pełny przebieg przy starcie — unikaj serii redeployów w krótkim czasie, bo
   wyczerpią limit godzinowy/dzienny.
8. **Nowa wersja danych:** build + `pipeline.publish` — strona i `forecast` same przechodzą na nowy
   `manifest.json`; redeploy nie jest potrzebny.
9. **Własna domena bucketu (krok do wykonania przed produkcją):** `r2.dev` służy do testów — ma limit
   żądań, brak cache Cloudflare i Cloudflare nie zaleca go do ruchu produkcyjnego. W Cloudflare → R2 →
   bucket → **Settings → Custom Domains → Connect Domain** podłącz domenę ze strefy w Cloudflare (np.
   `dane.example.pl`) i poczekaj na status *Active*. Przełączenie:
   - w Coolify ustaw `DATA_BASE_URL=https://dane.example.pl/` w usługach `web` **i** `forecast`, redeploy
     (dane w buckecie bez zmian — publikacja nie jest potrzebna);
   - sprawdź `curl -sI https://dane.example.pl/manifest.json` (`200`, `content-encoding: gzip`) i stronę
     (`/dane/…` → `206` dla `Range`);
   - opcjonalnie tryb wprost (ruch danych z pominięciem VPS, z cache Cloudflare): reguła CORS z punktu 5
     dla tej domeny, potem `DATA_DIRECT=1` w `web` i redeploy;
   - na koniec można wyłączyć publiczny dostęp przez `r2.dev`.

Weryfikacja: `curl -sI <DATA_BASE_URL>manifest.json` (`content-encoding: gzip`, `cache-control: no-cache`).
Tryb proxy: `curl -s -D - -o /dev/null -H 'Range: bytes=0-99' https://<domena strony>/dane/v/<build>/lasy.pmtiles`
→ `206`. Tryb wprost: `curl -s -D - -o /dev/null -H 'Origin: https://example.org' -H 'Range: bytes=0-99' <DATA_BASE_URL>v/<build>/lasy.pmtiles`
→ `206` oraz `access-control-allow-origin` (brak tego nagłówka = brak reguły CORS, mapa się nie wczyta).

## Dane i licencje

- Siedliska: Bank Danych o Lasach (BDL), PGL Lasy Państwowe, stan 2026. Dane poglądowe, udostępniane w oparciu
  o regulamin BDL i ustawę o dostępie do informacji publicznej (szczegóły: `docs/data/bdl.md`).
- Pogoda: [Open-Meteo](https://open-meteo.com/) (darmowe API, użycie niekomercyjne).
- Rezerwaty: Generalna Dyrekcja Ochrony Środowiska (GDOŚ), WFS sdi.gdos.gov.pl.
- Podkłady: ortofotomapa i mapa topograficzna GUGiK (geoportal.gov.pl).
- Mapa podkładowa: © OpenStreetMap.
