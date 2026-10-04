# L. Wilgotność miejsca (bufor wodny wydzielenia) i borowik: dąb, trawa, słońce — projekt

Data: 2026-10-04. Status: zaakceptowany w rozmowie (sekcje 1–5), autor spec: Claude.

## Problem

Zgłoszenie z terenu (2026-10-04, kratka pogodowa `505_176`, `w` = 0,80, czynnik `dry` na granicy progu):

| | 02-32-1-04-379-b-99 (pusto) | 02-32-1-04-370-a-00 (pełny koszyk) |
|---|---|---|
| drzewostan | SO 97 lat, zadrzewienie 0,6, dąb i buk w domieszce | SO 62 lata, zadrzewienie 0,9, BRZ, OL |
| siedlisko / wilgotność / gleba | BMSW / `S` / `Bw` | BMSW / `SS` / `Bgms` |
| TWI (mediana) | 7,05 (MID) | 7,48 (WET) |
| wyniesienie nad otoczenie 500 m (TPI) | +11,8 m, rozpiętość 25,5 m | +7,5 m (skarpa) |
| odległość od Stawu Pustelnik (30 ha) | 1161 m | 3 m |
| h borowik / podgrzybek | 70 / 70 | 63 / 63 |

Teren: 379-b bardzo pagórkowate i zacienione — sucho, brak grzybów (także w sąsiednich pomarańczowych). Wzdłuż stawu:
podgrzybki, koźlarze, prawdziwki, borowiki sosnowe.

Przyczyny: (1) obie lokalizacje mają ten sam `w` (siatka 0,1°); (2) `h` nie zna odległości od wody ani
położenia w rzeźbie, `moist` jest zneutralizowany, TWI działa tylko dla dwóch gatunków; (3) wilgotność miejsca
ma znaczenie **warunkowe** — w suszy wygrywają miejsca wilgotne, w mokrym okresie nie — a model `h × w`
nie ma interakcji. Walidacja na całym sezonie słusznie nie widziała efektu statycznego.

Dodatkowo (wiedza użytkownika, zgodna z walidacją): borowik lubi dąb, trawę i słońce. Kara `veg` (`ZAD` 0,7)
obniża AUC siedliska borowika (ablacja: 0,530 → 0,548).

## Cel i kryteria sukcesu

1. Dla pogody z 2026-10-04 (`rain` = 0,797 w `505_176`) wynik borowika 370-a ≥ wynik 379-b + 8, a 379-b < 45
   (test na prawdziwych danych, `scripts/check_wet_case.py`).
2. Walidacja GBIF: AUC „w obrębie kratki i dnia” dla `h × w_eff` nie gorsze o więcej niż 0,01 od `h × w`;
   raport podaje osobno dni suche (`rain` < 0,8) z liczebnością.
3. AUC siedliska borowika nie gorsze niż przed zmianą (0,530 na tych samych danych).
4. Bez `wet` w kafelkach lub bez `rain` w pogodzie klient zachowuje się jak dziś.

## 1. Wskaźnik `wet` (statyczny, pipeline)

Surowa wilgotność wydzielenia = suma ważona składników 0–1 (parametry w `species.yaml`, sekcja `water:`):

| składnik | źródło | wartość | waga |
|---|---|---|---|
| `water` | OSM: `natural=water` ≥ 0,5 ha, `waterway=river`/`riverbank`, `natural=wetland` | 1 do 50 m od krawędzi wydzielenia, liniowo do 0 przy 500 m | 0,30 |
| `ditch` | OSM: `waterway=ditch|drain|stream|canal` | 1 do 20 m, liniowo do 0 przy 150 m | 0,15 |
| `valley` | TPI 500 m (GLO-30) | 1 − percentyl TPI w obszarze | 0,15 |
| `habitat` | typ siedliskowy i kod wilgotności BDL | max(wartość typu, wartość kodu), tabele niżej | 0,15 |
| `soil` | grupa/podtyp gleby BDL | G, OG, OGS, MR, T, M, CZ → 1; MD, AU → 0,7; „g” w podtypie (oglejone, np. `Bgms`) → 0,5; reszta 0 | 0,15 |
| `twi` | mediana TWI | percentyl w obszarze | 0,10 |

Tabele siedliska: typ — olsy i bagienne (`OL*`, `BB`, `BGB`, `BMB`, `BMGB`, `LMB`) 1; łęgi (`LL*`) 0,8; zestawy
wilgotne (`bory_wilgotne`, `bory_mieszane_wilgotne`, `lasy_mieszane_wilgotne`, `lasy_wilgotne`) 0,6; `BS` 0;
`BSW`, `BGSW` 0,1; pozostałe 0,2. Kod wilgotności — `SU` 0; `S`, `SS` 0,2; `WSW` 0,5; `WW`, `WO` 0,6;
`LN`, `LP` 0,7; `LZ` 0,9; `BO`, `BM`, `BSO`, `BBM` 1.

Brak składnika (brak danych) → wartość neutralna 0,5 (dla `water`/`ditch` brak = brak wody w zasięgu = 0).
`wet` = percentyl surowej wartości wśród wszystkich wydzieleń × 100 (liczba całkowita 0–100); mediana = 50.
Kod powodu `wl`: przy `wet` ≥ 65 składnik o największym wkładzie ważonym (`water`, `ditch`, `valley`, `soil`,
`habitat`, `twi`); przy `wet` ≤ 35 `hilltop`, gdy `valley` < 0,25, inaczej `dry`; poza tym brak.

Rowy liczone na krótkim dystansie (pas przy rowie bywa wilgotny i trawiasty; dalej rów odwadnia).
Odsłonięcia drzewostanu nie uwzględniamy: zadrzewienie BDL dotyczy górnego piętra i nie oddaje zacienienia.
Ograniczenie: GLO-30 to model powierzchni (częściowo korony drzew) — wystarczy przy różnicach > 10 m; lidarowy
NMT GUGiK to możliwe rozszerzenie poza zakresem.

## 2. Wzór (klient i walidacja)

```
γ      = G ^ (1 − 2·wet/100)          G = 3
w_eff  = min(1, w · rain^(γ − 1))     dla rain > 0;  rain = 0 → w_eff = w
wynik  = round(h × w_eff)
```

Ten sam efekt co podniesienie składowej opadu do potęgi γ: przy `rain` = 1 brak zmiany; `wet` = 50 → γ = 1;
`wet` = 0 → γ = 3; `wet` = 100 → γ = 1/3. Brak `wet` → 50; brak `rain` → `w`.
Implementacje: `forecast/model.py: wet_adjust`, `web/js/data.js: adjustW`, wyrażenie MapLibre w `map.js`;
wspólne przypadki testowe `tests/fixtures/wet_cases.json` (pytest i node).

## 1b. Borowik: dąb, trawa, słońce (statyczne `h`)

- `factors.veg: {}` — bez kary za zadarnienie i ziele;
- `factors.density: [[0.9, 1.0], [1.0, 0.9]]` — bez kary za niskie zadrzewienie (kara za zwarcie zostaje);
- nowe opcjonalne pole gatunku `partner_weights` (kod → mnożnik 0–1, brak = 1): borowik
  `{DB: 1.0, BK: 0.9, SO: 0.85, SW: 0.85}`; `partner_score` mnoży wynik partnera przez wagę.
- kara za stromy stok południowy zostaje (ablacja obniża AUC).

## 3. Dane i klient

- `pipeline/fetch_water.py`: Overpass (mechanizm kafli/ponowień/cache z `fetch_parkings`), wynik
  `pipeline/data/woda.geojson` (kolumny `kind` ∈ {`water`, `ditch`}, geometria; poligony wód < 0,5 ha pominięte).
- `pipeline.terrain`: kolumna `tpi` (średnia po wydzieleniu z DEM − średnia w oknie 1 km × 1 km).
- `pipeline/wetness.py` (`python -m pipeline.wetness`): składniki + `wet` + `wl` → `pipeline/data/wetness.parquet`.
- `load_stands` dołącza `wet`, `wl` (left join); bez pliku — kolumny puste.
- kafelki `lasy`: atrybuty `wet` (int) i `wl` (gdy jest);
- centroidy: `index.json` dostaje `"extra": ["wet"]`, wiersz kończy się wartością `wet` (lub `null`); stary klient
  czyta `h` po indeksach i ignoruje ostatnią kolumnę — zmiana zgodna wstecz;
- `pogoda.json` i forecast bez zmian; `build.json` dostaje `wetness` (wagi, liczba wydzieleń z `wet`).
- web: `weatherFor(pogoda, cell, species, dayIdx, wet)` zwraca skorygowane `w` (i `w_raw`); popup, ranking,
  wykres i mapa przekazują `wet`.

## 4. Walidacja

`pipeline.validate --wet`: dla każdej obserwacji (wydzielenie, dzień) z pogodą historyczną losowanych jest do 20
wydzieleń z tej samej kratki (te same `w`, `rain`); AUC `h × w` vs `h × w_eff`, wszystkie dni i dni suche.
Wyniki w sekcji „Wilgotność miejsca” raportu. Mała próba (borowik ~80, podgrzybek ~37) — kryterium 2 jest
zabezpieczeniem, nie strojeniem; `G` i wagi pozostają eksperckie.

## 5. UI

- popup: wiersz „Wilgotność miejsca: wysoka/średnia/niska (powód)”; przy `lim` ∈ {`dry`, `dry_soil`} zdanie
  „W suszy to miejsce wypada lepiej/gorzej niż okolica” (gdy |w_eff − w| ≥ 0,05);
- „Szczegóły modelu”: wiersz „Wilgotność miejsca” z korektą w punktach procentowych;
- tekst o modelu (`content`/ui): krótki opis efektu. Bez przełącznika „tryb suszy”.

## Wydanie

Najpierw `web` (Coolify z `main`), potem `pipeline.publish`. Stary klient + nowe dane: działa jak dziś.
Nowy klient + stare dane: `wet` brak → neutralnie.
