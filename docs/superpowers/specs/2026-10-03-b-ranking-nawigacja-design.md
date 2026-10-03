# B. Ranking i nawigacja — projekt

Data: 2026-10-03
Status: do przeglądu
Zakres: usprawnienia 2 (Prowadź), 3 (czytelne nazwy), 4 (grupowanie), 5 (udostępnianie), 6 (promień i reset GPS).
Powiązane: A (strzałka trendu w wierszu rankingu — tylko jeśli A jest wdrożone), C (rezerwaty poza rankingiem).
Kolejność wdrażania specyfikacji: **C → A → B → D** (C najpierw, bo dziś mapa może polecać rezerwaty);
każda jest samodzielna, zależności między nimi są miękkie (opisane w „Powiązane”).

## 1. Cel

Ranking ma wskazywać 10 **różnych** miejsc z nazwą, którą da się odnaleźć w terenie, i pozwalać
do nich dojechać oraz je komuś wysłać.

**Kryterium sukcesu:** wiersz rankingu brzmi „Oddz. 368 · Leśn. Zieleniec · Nadl. Brzeg, 4,2 km płn.-wsch.”;
z popupu jednym kliknięciem otwiera się nawigacja; link do miejsca otwiera mapę z tym samym popupem.

## 2. Dane: `web/data/nazwy.json`

```json
{ "nadl": { "02-04": "Brzeg", ... }, "lesn": { "02-04-1-07": "Zieleniec", ... } }
```

- `nadl`: z `pipeline/bdl_fields.yaml` (`districts[].prefix` → `name`).
- `lesn`: z kolekcji BDL OGC API `lesnictwa` (pola `forest_range_name`, `adress_forest`).
  Pobranie per nadleśnictwo: `filter=adress_forest LIKE '<prefix>%'`, stronicowanie jak w `fetch_bdl`.
  Normalizacja klucza: usunąć białe znaki, wziąć pierwsze 4 segmenty po `-`
  (`"02-04-1-07-      -    -"` → `"02-04-1-07"`).
- Nowy moduł `pipeline/fetch_names.py` (`python -m pipeline.fetch_names`), wynik commitowany
  (kilka kB). Kroki w README po `fetch_bdl`.

Format `centroidy.json` się nie zmienia: klucze nazw wynikają z prefiksu `id`.

## 3. Grupowanie po oddziale (4) i nazwy (3)

Adres leśny: `RR-NN-O-LL-ODDZ-w-pp`. **Klucz oddziału** = pierwsze 5 segmentów
(`02-04-1-07-368`). Numer oddziału jest na słupkach oddziałowych w lesie.

`ranking.js`:
- `topN(centroids, pogoda, species, dayIdx, origin, radiusKm, n)` zwraca grupy:
  `{ key, best: {id, lat, lon, score}, count, distanceKm, bearing }`, gdzie
  `best` = wydzielenie o najwyższym wyniku w oddziale (remis: mniejsze `id`),
  `count` = liczba wydzieleń oddziału z wynikiem > 0 w promieniu,
  `distanceKm`, `bearing` liczone do `best`.
  Sortowanie jak dziś (wynik malejąco, potem klucz).
- `bearing(origin, point)` → jedna z 8 nazw: „płn.”, „płn.-wsch.”, „wsch.”, „płd.-wsch.”, „płd.”,
  „płd.-zach.”, „zach.”, „płn.-zach.”.
- Nowy moduł `web/js/names.js`: `placeName(id, nazwy)` → `{ oddz: "368", lesn: "Zieleniec" | null, nadl: "Brzeg" | null }`;
  `formatPlace(...)` → „Oddz. 368 · Leśn. Zieleniec · Nadl. Brzeg” (brakujące części pomijane;
  brak `nazwy.json` → „Oddz. 368 · 02-04-1-07”).

Wiersz rankingu: `[wynik][strzałka trendu z A, jeśli dostępna] Oddz. … · Leśn. … · Nadl. …`
w pierwszej linii, w drugiej `4,2 km płn.-wsch. · 3 wydz.` (pole `count`, „1 wydz.” też pokazujemy).
Klik → `flyToRow(best)` jak dziś.

Popup: nagłówek `formatPlace(...)`, pod nim małą czcionką pełne `id` wydzielenia.

`loadData` ładuje `nazwy.json` niezależnie (`Promise.allSettled`); awaria nie blokuje mapy.

## 4. Prowadź (2)

W popupie wiersz akcji:
- przycisk-link **„Prowadź”**: `https://www.google.com/maps/dir/?api=1&destination=<lat>,<lon>`
  (`target="_blank" rel="noopener"`); działa na Android/iOS/desktop,
- mniejszy link „OSM”: `https://www.openstreetmap.org/directions?route=%3B<lat>%2C<lon>`.
Cel: punkt kliknięcia (z rankingu: centroid `best`). Współrzędne do 5 miejsc po przecinku.
Funkcje `navUrls(lat, lon)` w `names.js` (czyste, testowane).

## 5. Udostępnianie (5)

### 5.1. Hash
`hash.js` dostaje parametr `w=<id wydzielenia>`: obecny w hashu, gdy otwarty jest popup;
zamknięcie popupu usuwa go. Walidacja: `^[0-9A-Za-z-]{1,40}$`, inaczej ignorowany.
Po starcie z `w` w hashu: po pierwszym `idle` z wczytanymi danymi `queryRenderedFeatures` w środku
mapy (`c`) po `id`; znaleziony → `showPopup`, nieznaleziony → nic (mapa tylko wycentrowana).

### 5.2. Przyciski
- Topbar: przycisk „Udostępnij” (ikona ⤴, `aria-label`): `navigator.share({ title, url: location.href })`;
  brak API lub błąd inny niż `AbortError` → `navigator.clipboard.writeText` + toast
  „Skopiowano link” (2 s, `role="status"`). Brak schowka → `prompt()` z linkiem.
- Popup: „Udostępnij miejsce” — ta sama funkcja; przed udostępnieniem hash ustawiony na
  `c` = punkt wydzielenia, `z = max(z, 15)`, `w = id`.

## 6. Promień i GPS (6)

- Nagłówek panelu: „Top 10 w promieniu” + `<select>` 5 / 10 / 20 / 40 km (kliknięcie selecta
  nie zwija panelu). Parametr hasha `r` (dozwolone 5, 10, 20, 40; inaczej 20).
- Pod nagłówkiem podpis: „od Twojej lokalizacji” albo „od środka mapy”.
- Przycisk ◎ jako przełącznik (`aria-pressed`): włączony → `gps` ustawiony, podświetlony;
  ponowne kliknięcie → `gps = null`, ranking od środka mapy. Błąd lokalizacji → stan wyłączony
  i podpis „Brak zgody na lokalizację — ranking od środka mapy”.

## 7. Testy

- pytest `tests/test_fetch_names.py`: normalizacja `adress_forest`, budowa `nazwy.json` z fixture,
  stronicowanie (mock sesji jak w `test_fetch_bdl`).
- node `ranking.test.js`: grupowanie po oddziale (best, count, remisy), promień, `bearing` (8 kierunków).
- node `names.test.js`: `placeName`/`formatPlace` (pełne, bez leśnictwa, bez pliku), `navUrls`.
- node `hash.test.js`: `r` (dozwolone/niedozwolone), `w` (walidacja), round-trip.

## 8. Poza zakresem
Najbliższa miejscowość (OSM), grupowanie sąsiednich oddziałów, nawigacja wewnątrz strony.
