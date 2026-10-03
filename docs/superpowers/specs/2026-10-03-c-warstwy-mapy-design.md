# C. Warstwy mapy — projekt

Data: 2026-10-03
Status: do przeglądu
Zakres: usprawnienia 7 (rezerwaty i zakazy wstępu), 12 (podkłady satelitarny i topograficzny).
Powiązane: B (ranking — rezerwaty z niego znikają).
Kolejność wdrażania specyfikacji: **C → A → B → D** (C najpierw, bo dziś mapa może polecać rezerwaty);
każda jest samodzielna, zależności między nimi są miękkie (opisane w „Powiązane”).

## 1. Cel

Mapa nie może polecać miejsc, w których nie wolno zbierać grzybów, a użytkownik ma widzieć drogi
leśne i teren.

**Kryterium sukcesu:** wydzielenia w rezerwatach są szare, kreskowane, opisane nazwą rezerwatu
i nie występują w rankingu; podkład można przełączyć na satelitę lub mapę topograficzną.

## 2. Rozpoznanie danych (2026-10-03)

- Wydzielenia BDL (pobrane): `forest_fun` = `GOSP` 96007, `REZ` 405, `REZ CZ` 96, brak 207.
- GDOŚ WFS `https://sdi.gdos.gov.pl/wfs`, warstwa `GDOS:Rezerwaty` (oficjalne granice, nazwy).
- Moduł BDL „Zakazy wstępu” (`/portal/zakazy-wstepu`) to aplikacja JS; katalog usług mapowych
  BDL zwraca 403. Maszynowo czytelne źródło **niepotwierdzone**.

## 3. Rezerwaty (7a)

### 3.1. Pipeline
- Nowy `pipeline/fetch_reserves.py` (`python -m pipeline.fetch_reserves`): WFS GetFeature
  `typeNames=GDOS:Rezerwaty`, `srsName=EPSG:4326`, filtr bbox obszaru; przycięcie do
  `pipeline/data/obszar.geojson`; zapis `pipeline/data/rezerwaty.geojson` z atrybutem `name`
  (commitowany; nazwa pola źródłowego i obsługiwany `outputFormat` do potwierdzenia w GetCapabilities/
  DescribeFeatureType w pierwszym kroku planu — fallback: GML przez `geopandas.read_file`).
- `build_tiles.py`:
  - nowy atrybut wydzielenia `rez` (nazwa rezerwatu lub `"rezerwat"`), gdy
    `forest_fun` zaczyna się od `REZ` **lub** centroid wydzielenia leży w poligonie z
    `rezerwaty.geojson` (nazwa z poligonu ma pierwszeństwo),
  - `bdl_fields.yaml` → `fields.fun: forest_fun`, wczytywane przez loader,
  - wydzielenia z `rez` **nie trafiają** do `centroidy.json`,
  - druga warstwa w PMTiles: `rezerwaty` (poligony + `name`), tippecanoe `-L rezerwaty:<plik>`.
- Atrybucja w stopce: „Rezerwaty: GDOŚ”.

### 3.2. Mapa (`map.js`)
- `fillColorExpression`/`fillOpacityExpression`: na początku `case` warunek `["has", "rez"]` →
  `COLORS.reserve = "#757575"`, krycie 0,5.
- Nowa warstwa `lasy-rez-hatch` na źródle `lasy` (`filter: ["has", "rez"]`, `fill-pattern: "hatch"`),
  więc kreskowane są też wydzielenia oznaczone tylko flagą BDL; wzór 8×8 px ukośnych linii
  generowany w `createMap` przez `map.addImage("hatch", {width, height, data})` (bez plików).
- `rezerwaty-line` (obrys `#6a1b9a`, 1,5 px) i `rezerwaty-label` (`symbol`, `text-field: name`,
  od zoomu 11). Etykiety wymagają `glyphs` w stylu — użyć
  `https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf` lub zrezygnować z etykiet,
  jeśli źródło fontów jest nieakceptowalne (decyzja w planie; wtedy nazwa tylko w popupie).
- Legenda: wpis „rezerwat — zbiór zabroniony” z kreskowanym kwadratem.

### 3.3. Popup
Gdy `props.rez`: zamiast wyniku ramka
„Rezerwat przyrody „<nazwa>” — zbieranie grzybów jest co do zasady zabronione.”
Tabela siedliska bez zmian, bez wykresu/trendu (A) i bez „Prowadź” (B).

## 4. Czasowe zakazy wstępu (7b)

1. **Spike (pierwsze zadanie planu, maks. ~1 h):** czy moduł BDL „Zakazy wstępu” korzysta z
   publicznego endpointu (zapytania XHR w przeglądarce), w jakim formacie, czy zawiera geometrię lub
   klucz nadleśnictwa/leśnictwa/oddziału i czy regulamin BDL pozwala na automatyczne pobieranie.
   Wynik zapisany w `docs/data/zakazy.md`.
2. **Zawsze:** w stopce i w popupie link „Sprawdź aktualne zakazy wstępu (BDL)” →
   `https://zakazywstepu.bdl.lasy.gov.pl/zakazy/`.
3. **Jeśli spike pozytywny (osobny etap planu):** `forecast/run.py` pobiera zakazy przy każdym
   przebiegu do `data/live/zakazy.json` (awaria pobrania nie blokuje `pogoda.json`);
   frontend nakłada je jako warstwę GeoJSON (czerwone kreskowanie), popup pokazuje
   „Zakaz wstępu do <data>”, ranking pomija wydzielenia pod zakazem.

Zagrożenie pożarowe nie jest osobną warstwą — w praktyce skutkuje zakazami wstępu.

## 5. Podkłady (12)

Przełącznik (kontrolka MapLibre w prawym górnym rogu, 3 przyciski radiowe), parametr hasha
`b ∈ {osm, orto, topo}`, domyślnie `osm`.

| klucz | źródło | uwagi |
|---|---|---|
| `osm` | `tile.openstreetmap.org` (obecny) | bez zmian |
| `orto` | Geoportal PZGiK ORTO WMS (`.../wss/service/PZGIK/ORTO/WMS/StandardResolution`) | `tiles` z `{bbox-epsg-3857}`, `tileSize: 256` |
| `topo` | Geoportal mapa topograficzna (WMS) | URL i nazwa warstwy do potwierdzenia |

- Pierwszy krok planu: GetCapabilities obu usług (URL, warstwa, EPSG:3857, warunki użycia).
  Jeśli Geoportal nie obsługuje 3857 dla topo, alternatywa: OpenTopoMap (`{a-c}.tile.opentopomap.org`).
- Implementacja: wszystkie trzy źródła rastrowe w stylu, przełączanie przez
  `setLayoutProperty(..., "visibility", ...)` (bez przeładowania stylu i warstw lasów).
- Na `orto`: `lasy-line` jaśniejsze (`#ffffff`, krycie 0,7), `fill-opacity` bez zmian.
- Atrybucja w stopce zależna od podkładu („Ortofotomapa: GUGiK”, „© OpenTopoMap” itd.).

## 6. Testy

- pytest `tests/test_fetch_reserves.py`: parsowanie odpowiedzi WFS (fixture), przycięcie.
- pytest `tests/test_build_tiles.py`: `rez` z flagi BDL, `rez` z przecięcia, pierwszeństwo nazwy GDOŚ,
  wykluczenie z centroidów, warstwa `rezerwaty` w wyjściu GeoJSONSeq.
- node `map.test.js`: wyrażenie koloru/krycia z gałęzią `rez`, definicje podkładów;
  `hash.test.js`: parametr `b`.

## 7. Poza zakresem
Natura 2000, parki krajobrazowe, obszary chronionego krajobrazu (zbiór dozwolony),
własne kafelki podkładu, tryb offline.
