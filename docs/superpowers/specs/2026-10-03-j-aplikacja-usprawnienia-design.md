# J. Usprawnienia aplikacji: parkingi, słabe strony siedliska, offline, stany ładowania — projekt

Data: 2026-10-03
Status: do akceptacji
Zakres: analiza zewnętrznych propozycji i wybór tych, które mają sens w obecnej architekturze (statyczna strona + statyczne dane w R2); parkingi z OSM jako nowa warstwa kafelków, „słabe strony siedliska” w popupie (po F/I), praca offline (PWA), stan ładowania rankingu, aktualny tytuł strony.
Poza zakresem: zgłaszanie znalezisk przez użytkowników (wymaga backendu — zastępuje je walidacja na GBIF, spec H), warstwa zakazów wstępu (serwis BDL `mapserver.bdl.lasy.gov.pl/.../Mapa_zakazow_wstepu_do_lasu/MapServer` zwraca 403 dla żądań spoza ich strony — zostaje link), zmiana palety legendy.

## 1. Analiza propozycji (Gemini, 2026-10-03)

| Propozycja | Stan | Decyzja |
|---|---|---|
| Przycisk „Zlokalizuj mnie” | **Jest** — `#locate` (◎), ranking od lokalizacji, `flyTo` | nic |
| Szczegóły oceny w popupie | **Częściowo** — popup ma gatunek panujący, wiek, TSL, składowe pogody, czynnik ograniczający, wykres 8 dni | dodać „słabe strony siedliska” (§3) — z F/I model ma czynniki, których popup nie zna |
| „Nawiguj” (Google Maps) | **Jest** — „Prowadź” i „OSM” w popupie (`actionLinks`) | nic |
| Parkingi leśne z BDL | Paczki BDL **nie mają** warstwy parkingów (tylko `G_SUBAREA`, `G_COMPARTMENT`, `G_FOREST_RANGE`, `G_INSPECTORATE`) | parkingi z OSM (§2) |
| Offline / PWA | **Brak** | service worker (§4) |
| Zgłaszanie zbiorów | Brak, wymaga backendu i moderacji | poza zakresem; kalibracja przez GBIF (spec H) |
| Stany ładowania | Ranking nie pokazuje, że trwa pobieranie kafelków centroidów | stan „Ładowanie…” (§5) |
| Bottom sheet na telefonie | **Jest** — panel rankingu zwijany (`#panel-toggle`) | nic |
| Błędy API pogody | **Jest** — baner `#stale`, timeouty fetchy, mapa koloruje samym `h` | nic |
| Rozróżnienie gatunków | **Jest** — 6 gatunków z różnymi partnerami, wiekiem, TSL, sezonem i progami | nic (F/I zwiększają różnice) |
| Legenda dla daltonistów | Paleta szary → jasnożółty → żółty → pomarańczowy → czerwony jest sekwencyjna jasnościowo (poza szarym „brak”) | nic |

Dodatkowo znalezione: tytuł strony „Grzyby w opolskiem” jest nieaktualny (obszar to RDLP Katowice i Wrocław) → „Gdzie na grzyby?” (§5).

## 2. Parkingi z OpenStreetMap

- **Pobieranie:** `python -m pipeline.fetch_parkings` → Overpass API (`https://overpass-api.de/api/interpreter`, nagłówek `User-Agent: gdzie-na-grzyby`), zapytanie po bbox `obszar.geojson` dzielonym na kafle 0,5° (limit czasu Overpass): `nwr["amenity"="parking"]` z `out center tags;`. Cache surowych odpowiedzi w `pipeline/data/raw/osm/parking_<lat>_<lon>.json`; ponowienie po 429/504 z backoffem 30 s, maks. 3.
- **Filtr:** odrzucone `access ∈ {private, no, customers, permit}`, `parking ∈ {underground, multi-storey, rooftop}`; zostają punkty w odległości ≤ 300 m od wydzieleń (bufor sumy wydzieleń w EPSG:2180) — parkingi przy lasach, nie w centrach miast.
- **Wynik:** `pipeline/data/parkingi.geojson` (punkty; atrybuty `name` opcjonalnie, `fee` = `"yes"`/`"no"`/brak, `osm` = `"n123"`/`"w123"`).
- **Kafelki:** `build` dodaje warstwę `parkingi` do `lasy.pmtiles` (`-L parkingi:…`), gdy plik istnieje; punkty mają `minzoom` 11 przez rozszerzenie GeoJSONSeq `"tippecanoe": {"minzoom": 11}` w każdym obiekcie.
- **Mapa:** warstwa `parkingi` typu `symbol` z ikoną „P” generowaną na canvasie (jak `hatchPattern`; `addImage("parking", …)` — styl nie ma glifów, więc bez `text-field`), od zoomu 11. Kliknięcie parkingu → mały popup: „Parking” + nazwa (jeśli jest) + „płatny”/„bezpłatny” (jeśli `fee`) + „Prowadź” (`actionLinks`).
- **Kontrakt:** `docs/data/api.md` — nowa warstwa `parkingi` w `lasy.pmtiles` (zmiana wstecznie zgodna). Atrybucja OSM już jest.

## 3. Słabe strony siedliska w popupie

- **Pipeline:** `build_tiles.compute_features` dla każdego gatunku liczy `habitat_components` (spec H/F/I) i zapisuje atrybut `hl_<gatunek>` = nazwa najsłabszego czynnika spośród modyfikatorów (czynniki F i I oraz `habitat`, `age`), gdy jego wartość < 0.8 i `h_<gatunek>` ≥ 20; inaczej atrybut pominięty (próg 20 ogranicza rozmiar kafelków przy 18 gatunkach ze specu K — słabe strony mają sens tylko tam, gdzie siedlisko w ogóle się liczy). Kody: nazwy czynników (`veg`, `moist`, `degr`, `soil`, `damage`, `density`, `twi`, `exposure`, `habitat`, `age`).
- **Klient:** `HAB_LIM_TEXT` w `web/js/popup.js`: `veg` „Ogranicza siedlisko: gęste runo/zadarnienie”, `moist` „…: zbyt mokre (bagienne)”, `degr` „…: siedlisko zniekształcone”, `soil` „…: mniej korzystna gleba”, `damage` „…: uszkodzony drzewostan”, `density` „…: zadrzewienie (za rzadko lub za gęsto)”, `twi` „…: położenie (za sucho lub za mokro)”, `exposure` „…: stromy stok południowy”, `habitat` „…: typ siedliskowy mniej korzystny”, `age` „…: wiek drzewostanu”. Wyświetlane w trybie jednego gatunku pod oceną siedliska, gdy atrybut jest; nieznany kod → nic.
- **Kontrakt:** nowy opcjonalny atrybut `hl_<gatunek>` w warstwie `lasy` (`docs/data/api.md`).

## 4. Praca offline (PWA)

- `web/manifest.webmanifest` (nazwa „Gdzie na grzyby?”, `short_name` „Grzyby”, `display: standalone`, kolor paska jak `--bar`, ikona SVG generowana raz i commitowana w `web/icons/icon.svg`), `<link rel="manifest">` w `index.html`.
- `web/sw.js` (rejestrowany w `ui.js` tylko gdy `"serviceWorker" in navigator` i strona nie jest `file:`):
  - **precache** powłoki: `index.html`, `css/app.css`, `js/*.js`, `vendor/*`, `manifest.webmanifest`, ikona; nazwa cache z wersją `grzyby-shell-<N>` (stała w `sw.js`, podbijana przy zmianie listy plików); przy `activate` usuwane stare cache `grzyby-*` spoza bieżących;
  - **network-first z timeoutem 4 s, fallback do cache:** `config.json`, `manifest.json`, `live/pogoda.json` (w trybach lokalnym, proxy `/dane/` i bezpośrednim — po końcówce ścieżki);
  - **cache-first:** pliki wersjonowane `…/v/<build>/…` (niezmienne), także żądania `Range` do `lasy.pmtiles` — klucz cache = URL + `#range=<wartość nagłówka>` (Cache API nie obsługuje Range), odpowiedź 206 zapisywana jako 200 z nagłówkami `Content-Range`, odtwarzana jako 206; limit 3000 wpisów w cache `grzyby-data`, nadmiar usuwany od najstarszych;
  - **podkłady (OSM, GUGiK):** stale-while-revalidate w `grzyby-base`, limit 2000 wpisów — tylko kafle już oglądane (bez masowego pobierania, zgodnie z zasadami korzystania z kafli OSM);
  - wszystko inne: przepuszczane bez cache.
- **UX:** gdy `navigator.onLine === false` przy starcie albo fetch pogody padł i odpowiedź przyszła z cache — baner „Tryb offline — dane z <data generated_at>”. Przycisk „Zapisz okolicę na offline” poza zakresem (masowe pobieranie).
- **Bezpieczeństwo wdrożenia:** `sw.js` serwowany z `Cache-Control: no-cache` (nginx, `docker/nginx*.conf`); w razie problemów wyłącznik: plik `sw.js` z samym `self.registration.unregister()` — opisany w `docs/`.

## 5. Drobne

- Ranking: na czas pobierania kafelków centroidów lista dostaje `aria-busy="true"` i jeden element „Ładowanie…”; po wyniku/błędzie `aria-busy="false"`.
- Tytuł strony: `<title>Gdzie na grzyby?</title>`.

## 6. Testy

- `tests/test_fetch_parkings.py`: zapytanie Overpass (podział bbox na kafle), filtr `access`/`parking`, filtr odległości od lasu, cache, format GeoJSON.
- `tests/test_build_tiles.py` / `tests/test_build.py`: `hl_<gatunek>` (próg 0.8, brak przy `h = 0`), warstwa `parkingi` w poleceniu tippecanoe tylko gdy plik istnieje.
- `web/tests/popup.test.js`: tekst `hl_*`, popup parkingu; `web/tests/map.test.js`: warstwa `parkingi`.
- `web/tests/sw.test.js`: czyste funkcje z `web/sw-core.js` (klasyfikacja żądania → strategia, klucz cache dla Range, wybór wpisów do usunięcia ponad limit). `sw-core.js` to klasyczny skrypt (service worker modułowy nie działa we wszystkich przeglądarkach) ładowany w `sw.js` przez `importScripts("sw-core.js")`, definiujący `self.SWCore`; test ładuje go w Node przez `vm.runInNewContext`.
- `web/tests/ranking.test.js` lub `ui`: stan ładowania.
