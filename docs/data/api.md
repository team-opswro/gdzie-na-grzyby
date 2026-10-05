# Kontrakt danych (publiczne „statyczne API” na R2)

Strona i przyszła aplikacja mobilna czytają te same pliki z publicznego bucketu (Cloudflare R2,
lokalnie katalog `pipeline/data/out/`). Ten dokument opisuje, co klient może założyć.
Adres bazowy `DATA_BASE_URL` (np. `https://pub-….r2.dev/` albo własna domena) zawsze z końcowym `/`
(klient powinien go dopisać, jeśli go brak).

## Układ

```
manifest.json                         wskaźnik bieżącej wersji (no-cache)
live/pogoda.json                      prognoza, nadpisywana 2× dziennie (no-cache)
v/<build>/lasy.pmtiles                kafelki wektorowe (immutable)
v/<build>/centroidy/index.json        indeks kafelków centroidów (immutable)
v/<build>/centroidy/<lat0>_<lon0>.json  kafelek centroidów 0,5° (immutable)
v/<build>/grid.json                   siatka pogodowa 0,1° (immutable)
v/<build>/nazwy.json                  nazwy nadleśnictw i leśnictw (immutable)
v/<build>/gatunki.json                treści i parametry gatunków (immutable)
v/<build>/build.json                  metadane builda (informacyjnie, immutable): liczniki, `h_hist`
                                      (liczba wydzieleń w przedziałach h 0–9 … 90–100 per gatunek),
                                      `terrain` (progi tercyli TWI, źródło NMT) gdy liczono teren
```

`<build>` = `YYYYMMDD-HHMM` (UTC, czas publikacji) + `-` + 7 znaków hasha gita, np.
`20261003-1812-1920064`. Wersje są niezmienne: raz wysłany plik pod `v/<build>/` nigdy się nie zmienia.
Publikacja (`python -m pipeline.publish`) wysyła najpierw wszystkie pliki wersji, a `manifest.json`
na końcu — przerwana publikacja zostawia działającą poprzednią wersję. Bucket trzyma 3 najnowsze
wersje (`--keep 3`), więc klient z manifestem sprzed kilku publikacji może dostać 404 — wtedy
powinien pobrać `manifest.json` ponownie.

## Nagłówki

| Plik | `Content-Type` | `Content-Encoding` | `Cache-Control` |
|---|---|---|---|
| `manifest.json`, `live/pogoda.json` | `application/json` | `gzip` | `no-cache` |
| `v/<build>/**/*.json` | `application/json` | `gzip` | `public, max-age=31536000, immutable` |
| `v/<build>/lasy.pmtiles` | `application/octet-stream` | — (bez kompresji, Range) | `public, max-age=31536000, immutable` |

- Pliki JSON są zapisane w buckecie już skompresowane gzipem (R2 nie kompresuje w locie) i wysyłane
  z `Content-Encoding: gzip` klientom z `Accept-Encoding: gzip`; przeglądarki i typowe klienty HTTP
  rozpakowują je przezroczyście. Klientowi bez `Accept-Encoding` Cloudflare oddaje treść rozpakowaną
  (sprawdzone na `r2.dev`). Bezpiecznie: rozpoznawać gzip po pierwszych bajtach `1f 8b`.
- `lasy.pmtiles` czytany zapytaniami `Range` (odpowiedź `206 Partial Content`).
- CORS: `GET`, `HEAD` z dowolnego originu (`*`); dozwolone nagłówki żądania `Range`, `If-Match`,
  `If-None-Match`; eksponowane `ETag`, `Content-Range`, `Content-Length`.
  Reguła CORS jest konfiguracją bucketu (panel R2 albo `publish --cors` z tokenem Admin) — patrz README,
  „Wdrożenie z R2”. Aplikacje natywne czytają bucket wprost (`DATA_BASE_URL`) i CORS nie potrzebują.
  Strona WWW domyślnie czyta te same pliki przez proxy nginx pod własną domeną (`/dane/` → `DATA_BASE_URL`,
  bez CORS; nagłówki `Content-Encoding`, `Cache-Control`, `ETag`, `Content-Range` i status `206`
  przechodzą bez zmian), a wprost z bucketu tylko z `DATA_DIRECT=1` (wtedy reguła CORS jest wymagana).

## `manifest.json`

```json
{
 "build": "20261003-1812-1920064",
 "base": "v/20261003-1812-1920064/",
 "generated_at": "2026-10-03T18:12:00Z",
 "files": {
  "lasy": "lasy.pmtiles",
  "centroidy": "centroidy/index.json",
  "grid": "grid.json",
  "nazwy": "nazwy.json",
  "gatunki": "gatunki.json"
 }
}
```

URL pliku = `DATA_BASE_URL + base + files[klucz]`. Klient nie składa ścieżek `v/…` sam — zawsze przez
manifest. Prognoza nie należy do wersji: `DATA_BASE_URL + "live/pogoda.json"`.

## `lasy.pmtiles`

PMTiles v3, kafelki wektorowe MVT, zoom 8–14 (powyżej 14 — overzoom). Warstwy:

- `lasy` — wydzielenia drzewostanowe (poligony). Atrybuty:
  - `id` — adres leśny BDL bez białych znaków, np. `02-40-1-12-363-i-00`,
  - `cell` — identyfikator komórki pogodowej (`grid.json`, `pogoda.json`),
  - `sp` — kod gatunku panującego (BDL), `age` — jego wiek (lata; może brakować), `hab` — kod typu siedliska,
  - `h_<gatunek>` — ocena siedliska 0–100 dla każdego gatunku z `gatunki.json`
    (np. `h_borowik`, `h_kurka`); wynik dnia = `round(h × w)`, gdzie `w` z `pogoda.json`;
    `h` uwzględnia partnera drzewnego i jego wiek, typ siedliskowy oraz (jako modyfikatory)
    pokrywę runa, wilgotność, degradację, glebę, uszkodzenia i zadrzewienie z BDL oraz położenie
    w terenie (wilgotność topograficzna TWI, strome stoki południowe) z Copernicus DEM GLO-30;
    **brak atrybutu `h_<gatunek>` = 0** (zera nie są zapisywane, żeby zmniejszyć kafelki),
  - `hl_<gatunek>` — „słaba strona siedliska”: nazwa najsłabszego modyfikatora (`veg`, `moist`, `degr`,
    `soil`, `damage`, `density`, `twi`, `exposure`, `habitat`, `age`), gdy jego mnożnik < 0,8, a
    `h_<gatunek>` ≥ 20; opcjonalny (brak = brak wyraźnej słabej strony),
  - `rez` — nazwa rezerwatu (lub `"rezerwat"`), gdy wydzielenie leży w rezerwacie (zbieranie zabronione),
  - `wet` — wilgotność miejsca 0–100 (percentyl w obszarze, mediana 50; spec L): bufor wodny wydzielenia
    z bliskości wód stojących, rzek i mokradeł (OSM) oraz położenia w rzeźbie (TPI z GLO-30); opcjonalny.
    Gdy jest, klient koryguje mnożnik pogody: `w_eff = min(1, w · m^(γ−1))`, `γ = G^(1 − 2·wet/100)`,
    `G` = `wet_gamma` gatunku z `gatunki.json` (brak = 3), `m` = `moist` z `pogoda.json` (spec M), a gdy go
    brak (plik sprzed specu M) — `rain`; `m` = 0 lub brak `wet`/`m` → `w` bez zmian; wynik dnia = `round(h × w_eff)`,
  - `wl` — powód wartości `wet` (tylko przy `wet` ≥ 65 lub ≤ 35): `water` (blisko wody), `valley` (obniżenie),
    `hilltop` (wyniesienie), `dry` (z dala od wody); opcjonalny; w przyszłości mogą dojść inne kody.
- `rezerwaty` — obrysy rezerwatów przyrody (GDOŚ), atrybut `name` (opcjonalny).
- `parkingi` — parkingi z OpenStreetMap (punkty), atrybuty:
  - `osm` — identyfikator OSM (`"n<id>"`, `"w<id>"` lub `"r<id>"`),
  - `name` — nazwa parkingu (opcjonalna),
  - `fee` — `"yes"` (płatny) lub `"no"` (bezpłatny) (opcjonalny);
  - widoczna od zoomu 11.
  Źródło: © OpenStreetMap contributors, ODbL.

Zoomy 8–10 warstwy `lasy` mają uproszczoną kopię wydzieleń: tylko `cell`, `rez`, `wet` i `h_<gatunek>`
(bez `id`, `sp`, `age`, `hab`, `hl_*`, `wl`), a przy za dużym kafelku najmniejsze poligony są doklejane do sąsiednich
(`--coalesce-smallest-as-needed`) — kolor mapy jest przybliżony, ale las nie ma dziur. Pełne atrybuty od zoomu 11;
klient poniżej zoomu 11 nie otwiera popupu wydzielenia, tylko przybliża mapę. (Do buildu `20261004-1408-12d72c4`
włącznie: pełne atrybuty na wszystkich zoomach i `--drop-smallest-as-needed`, które na z8–z10 usuwało 10–60%
powierzchni lasów.)

## Centroidy (ranking „najlepsze miejsca w promieniu”)

`centroidy/index.json`:

```json
{"tile": 0.5, "species": ["borowik", "podgrzybek", "kurka", "kozlarz", "maslak", "rydz"],
 "extra": ["wet"], "tiles": ["49.0_18.5", "49.0_19.0", "…"]}
```

Kafelek `centroidy/<lat0>_<lon0>.json`, gdzie `lat0 = floor(lat / 0.5) × 0.5`,
`lon0 = floor(lon / 0.5) × 0.5`, zapis z jedną cyfrą po przecinku (`50.5_17.0`). Istnieją tylko kafelki
wymienione w `tiles` (pozostałe → 404, klient ich nie pobiera):

```json
{"rows": [["02-34-1-15-542-f-00", 49.43326, 18.98704, "494_189", 12, 0, 18, 0, 0, 100, 63], …]}
```

Wiersz = `[id, lat, lon, cell, h_<species[0]>, h_<species[1]>, …, <extra[0]>, …]` — oceny siedliska
w kolejności `index.species`, potem kolumny wymienione w `index.extra` (opcjonalne; dziś `wet` — wilgotność
miejsca jak w kafelkach, `null` gdy brak). Klient czyta `h` po indeksach, więc kolumny `extra` na końcu nie
zmieniają ich położenia. Zawiera tylko wydzielenia z maksymalną oceną siedliska ≥ 40, bez rezerwatów; punkt to
punkt reprezentatywny poligonu (leży wewnątrz). Ranking w promieniu R: pobierz kafelki przecinające
bbox koła, przefiltruj wiersze po odległości, policz `round(h × w)` z pogodą komórki `cell` (z `wet` —
`round(h × w_eff)`, jak w kafelkach).

## `grid.json`

```json
{"step": 0.1, "cells": [{"id": "493_189", "lat": 49.35, "lon": 18.95}, …]}
```

Komórki siatki 0,1° zawierające las; `id` = `"<floor(lat×10)>_<floor(lon×10)>"`, `lat`/`lon` = środek
komórki. Kontener `forecast` pobiera z Open-Meteo pogodę dla tych punktów.

## `nazwy.json`

```json
{"nadl": {"02-01": "Andrychów", …}, "lesn": {"02-01-1-01": "Polanka Wielka", …}}
```

Klucze to prefiksy adresu leśnego `id`: nadleśnictwo `RR-NN`, leśnictwo `RR-NN-O-LL`.

## `gatunki.json`

`{"reviewed": bool, "species": [...]}` — lista gatunków w kolejności wyświetlania. Element:
`key` (np. `borowik`, ten sam co w `h_<key>` i `pogoda.json`), `name`, `latin`,
`season` (`{"start": "MM-DD", "end": "MM-DD"}`), `partners` (nazwy drzew), `habitats_preferred`,
`habitats_adjacent` (nazwy siedlisk), `age_min`, `wet_gamma` (siła efektu wilgotności miejsca `G`, ≥ 1;
1 = brak efektu; spec L), `description` i pozostałe pola treści z `content/gatunki.yaml` (nowe pola mogą
dochodzić). `reviewed: false` — treści niezweryfikowane przez
mykologa.

## `live/pogoda.json`

Generowany przez kontener `forecast` o 05:00 i 14:00 (`Europe/Warsaw`) i przy jego starcie;
schemat: `schema/pogoda.schema.json`.

```json
{
 "generated_at": "2026-10-03T14:00:12+02:00",
 "days": ["2026-10-02", "2026-10-03", "…", "2026-10-09"],
 "wx": {"493_189": {"rain_mm": [0.0, …], "soil_t": [9.8, …], "soil_m": [0.312, …], "dry_days": [9, …]}},
 "cells": {
  "493_189": {
   "borowik": {"w": [0.41, …], "rain": [0.8, …], "moist": [0.6, …], "temp": [0.9, …], "season": [1.0, …],
               "lim": ["dry", null, …]}
  }
 }
}
```

- `days` — 8 dni: wczoraj, dziś i 6 kolejnych; każda tablica dzienna ma 8 elementów w tej kolejności.
- `cells[cell][gatunek]` — mnożnik pogodowy `w` (0–1) i jego składowe `rain` (impuls: ważony opad sprzed
  5–21 dni), `moist` (wilgotność podłoża teraz z bilansu wody: opad − 0,8·ET0, wiadro 25 mm; od spec M,
  w starszych plikach i przy braku ET0 w prognozie brak), `temp`, `season` (0–1); `w = rain × moist × temp × season × pulse × frost` (≤ 1);
  opcjonalnie `pulse` (1.0–1.2, premia za ochłodzenie gleby) i `frost` (0–1, kara za niedawny przymrozek) —
  pomijane, gdy przez wszystkie dni wynoszą 1.0 (brak = 1.0); plik zapisywany bez zbędnych spacji;
  `lim` — czynnik ograniczający dnia: `dry` (za mało opadu w oknie impulsu), `dry_soil`
  (przesuszone podłoże — od spec M liczone z `moist`, wcześniej z wilgotności gleby Open-Meteo), `cold`, `hot`,
  `season` (poza sezonem), `frost` (niedawny przymrozek) albo `null`.
- `wx[cell]` — wartości, z których liczony jest mnożnik dnia: `rain_mm` (suma
  opadu w oknie poprzedzających dni, mm), `soil_t` (średnia temperatura gleby na 6 cm z ostatnich dni,
  °C), `soil_m` (średnia wilgotność gleby 3–9 cm z ostatnich dni, m³/m³). Gdy prognoza zawiera nowe
  zmienne Open-Meteo, opcjonalnie dodawane są: `et0_mm` (suma parowania odniesienia ET0 w tym samym
  oknie, mm), `soil_m_deep` (średnia wilgotność gleby 9–27 cm, m³/m³), `t2m_min` (minimum temperatury
  powietrza z ostatnich 7 dni, °C), `water` (zapas wody w podłożu na początek dnia, 0–1; spec M).
  Zawsze (od spec M; w starszych plikach brak): `dry_days` — pełne dni bez opadu ≥ 1 mm przed danym dniem
  (liczba całkowita; maksymalnie długość historii serii, ok. 30).
- Prognoza starsza niż 36 h jest nieaktualna (strona pokazuje wtedy baner i samą ocenę siedliska).

## Wersjonowanie i zgodność

- W obrębie prefiksu `v/` zmiany są tylko wstecznie zgodne: nowe pola i nowe pliki mogą dochodzić,
  istniejące pola nie zmieniają znaczenia ani typu. Klient ignoruje nieznane pola.
- Zmiana niekompatybilna (inny format wiersza centroidów, inna skala `h`, inny układ manifestu)
  = nowy prefiks `v2/` i osobny `manifest.v2.json` (lub `v2/manifest.json`); stare `v/` i `manifest.json`
  są utrzymywane, dopóki wspierani klienci z nich korzystają.
- `live/pogoda.json` podlega tej samej zasadzie (nowe pola dopuszczalne, zmiana znaczenia → `live/v2/`).

### Wydanie modelu v2 (18 gatunków, grupy, pomijane zerowe `h_*`)

Kolejność: **najpierw wdrożenie `web` i `forecast` z tej wersji kodu, potem `pipeline.publish` nowych
danych**. Stary klient działa z nowymi danymi bez błędów, ale w trybie „Wszystkie gatunki” mapa liczy
tylko 6 dawnych gatunków (zaszyta lista), a popup i ranking już 18 — wyniki się rozjeżdżają; stary
kontener `forecast` nie liczy pogody dla 12 nowych gatunków.

## Źródła i licencje

- Bank Danych o Lasach (BDL), PGL Lasy Państwowe — wydzielenia i opisy taksacyjne.
- Rezerwaty przyrody: GDOŚ. Parkingi i wody (wilgotność miejsca): © OpenStreetMap (ODbL), wycinki Geofabrik.
- Pogoda: Open-Meteo (CC BY 4.0).
- Model terenu: Copernicus DEM GLO-30 © DLR e.V. 2010–2014 i © Airbus Defence and Space GmbH
  2014–2018, dostarczone w ramach programu Copernicus.
