# Praca offline (PWA)

Aplikacja działa jako progresywna aplikacja webowa (PWA) dzięki service workerowi (`web/sw.js`).

## Co jest cache'owane

- **Powłoka aplikacji** (`grzyby-shell-<N>`): `index.html`, CSS, JS, biblioteki z `vendor/`, manifest i ikona
  (prekeszowane przy instalacji); także ostatnie `config.json`, `manifest.json`, `pogoda.json`.
  `SHELL_VERSION` w `web/sw-core.js` podbija się przy zmianie listy plików powłoki — nie przy każdej
  zmianie kodu (powłoka jest network-first, więc nowe wdrożenie widać od razu).
- **Dane wersjonowane** (`grzyby-data`): pliki pod `/v/<build>/`, w tym `lasy.pmtiles`.
  Żądania `Range` zapisywane są pod kluczem `URL?__range=<nagłówek>` (Cache API pomija fragment `#`
  przy dopasowaniu, więc zakres musi być w zapytaniu) jako odpowiedź 200 z zachowanym nagłówkiem `Content-Range`;
  odtwarzane są jako prawidłowa odpowiedź 206.
- **Podkłady** (`grzyby-base`): kafle OSM i GUGiK — tylko już oglądane (stale-while-revalidate),
  bez masowego pobierania, zgodnie z zasadami korzystania z kafli.

## Strategie

- `config.json`, `manifest.json`, `live/pogoda.json`, pliki powłoki i wejście na stronę — **network-first**:
  po 4 s bez odpowiedzi kopia z cache, jeśli jest (inaczej dalej czekamy na sieć); offline — cache,
  a dla wejścia na stronę prekeszowany `index.html` (wszystkie tryby: lokalny, proxy `/dane/`, bucket).
- `/v/<build>/...` — **cache-first**.
- `tile.openstreetmap.org`, `mapy.geoportal.gov.pl` — **stale-while-revalidate**.
- Pozostałe żądania — przepuszczane bez cache.

## Limity

- `grzyby-data`: 3000 wpisów.
- `grzyby-base`: 2000 wpisów.
- Po przekroczeniu limitu usuwane są najstarsze wpisy.

## Wyłącznik

W razie problemów z service workerem zastąp `web/sw.js` wersją zawierającą tylko:

```js
self.registration.unregister();
```

Po podbiciu `SHELL_VERSION` w `web/sw-core.js` i wdrożeniu przeglądarka zastąpi stary worker,
który następnie się wyrejestruje.

## Tryb offline

Gdy `navigator.onLine === false` po załadowaniu prognozy, nad mapą pojawia się baner:
„Tryb offline — dane z <data>”, gdzie data ma format z okna „Jak to działa?”.
