# gdzie-na-grzyby

Hobbystyczna mapa szans na grzyby (borowik, podgrzybek, kurka, kozlarz, maślak, rydz) w woj. opolskim.
Wynik = siedlisko (statyczne kafelki z danych BDL) × pogoda (prognoza Open-Meteo, odświeżana 2× dziennie).
Projekt: `docs/superpowers/specs/2026-10-03-grzyby-opolskie-design.md`.

## Testy

```sh
.venv/bin/pytest -v                 # Python (model, pipeline, forecast, healthcheck)
node --test web/tests/*.test.js     # JS (podaj pliki jawnie; katalog nie działa na Node 22)
```

## Przebudowa danych statycznych (pipeline)

Wykonywana lokalnie; wynik (`web/data/lasy.pmtiles`, `centroidy.json`, `grid.json`) trafia do repozytorium.

```sh
python -m pipeline.area                            # obrys obszaru: opolskie + nadleśnictwa `whole: true` -> pipeline/data/obszar.geojson
python -m pipeline.fetch_bdl                       # pobranie danych BDL do pipeline/data/raw
podman build -f pipeline/Dockerfile -t grzyby-pipeline .      # (docker: to samo polecenie)
podman run --rm -v $PWD:/w -w /w grzyby-pipeline \
  python -m pipeline.build_tiles --bdl pipeline/data/raw --boundary pipeline/data/obszar.geojson --out web/data
```

## Uruchomienie lokalne (Docker Compose)

`docker-compose.yml` celowo nie publikuje portów (routing robi Coolify). Do testów lokalnych dodaj
tymczasowy plik override, np. `docker-compose.local.yml`:

```yaml
services:
  web:
    ports:
      - "8080:80"
```

```sh
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build -d
# otwórz http://localhost:8080
docker compose logs -f forecast     # przy starcie powstaje pogoda.json (wymaga internetu)
docker compose -f docker-compose.yml -f docker-compose.local.yml down -v
```

(Z Podmanem: `podman compose ...`; aby HEALTHCHECK działał, zbuduj w formacie docker: `BUILDAH_FORMAT=docker podman compose ... up --build`;
stan sprawdzisz `podman healthcheck run <kontener>`.)

**Serwowanie deweloperskie:** `python -m http.server` NIE obsługuje nagłówków Range, których wymaga PMTiles
(mapa się nie wczyta). Używaj stosu Compose albo serwera z obsługą Range.

## Wdrożenie w Coolify

Wymaga zdalnego repozytorium git i dostępu do panelu Coolify (nic nie jest pushowane automatycznie).

1. Wypchnij repozytorium (z `web/data/lasy.pmtiles`; jeśli > 50 MB, użyj Git LFS).
2. W Coolify: **New Resource -> Docker Compose** z repozytorium git, plik `docker-compose.yml`.
3. Usługa `web`: ustaw domenę (port 80); HTTPS załatwia Traefik w Coolify.
4. Usługa `forecast` nie potrzebuje domeny. Wolumen `weather` jest trwały (współdzielony: `forecast` zapisuje, `web` czyta).
5. Deploy. Przy starcie `forecast` jednorazowo generuje `pogoda.json`, potem cron o 05:00 i 14:00 (`Europe/Warsaw`).
   Healthcheck: `pogoda.json` młodszy niż 36 h.

## Dane i licencje

- Siedliska: Bank Danych o Lasach (BDL), PGL Lasy Państwowe, stan 2026. Dane poglądowe, udostępniane w oparciu
  o regulamin BDL i ustawę o dostępie do informacji publicznej (szczegóły: `docs/data/bdl.md`).
- Pogoda: [Open-Meteo](https://open-meteo.com/) (darmowe API, użycie niekomercyjne).
- Mapa podkładowa: © OpenStreetMap.
