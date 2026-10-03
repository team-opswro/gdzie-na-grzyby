# K. Więcej gatunków i tryb grupy — projekt

Data: 2026-10-03
Status: do akceptacji
Zakres: 12 nowych gatunków mikoryzowych (koźlarze, borowiki, podgrzybki, maślaki, rydz świerkowy), zawężenie „rydza” do rydza mleczaja, grupy gatunków w danych i tryb grupy w aplikacji („wszystkie koźlarze”).
Poza zakresem: borowik ceglastopory (decyzja 2026-10-03), gatunki spoza modelu drzewostanowego (kania, opieńka), gatunki trujące jako cel wyboru, zmiana formuły `round(h × w)`.

## 1. Cel

Grzybiarz myśli „idę na kozaki”, a nie „na koźlarza babkę”. Model wydzieleniowy (partner drzewny × wiek × siedlisko) dobrze opisuje gatunki mikoryzowe związane z konkretnymi drzewami, a BDL ma te drzewa: osika `OS` (56 tys. wpisów w piętrach drzewostanu), grab `GB` (55 tys.), modrzew `MD` (133 tys.), topola `TP` (4 tys.).

**Kryterium sukcesu:** `species.yaml` ma 18 gatunków w 5 grupach + kurkę; build i prognoza liczą je bez zmian w kodzie modelu; aplikacja pozwala wybrać gatunek, grupę albo wszystkie gatunki; dotychczasowe linki (`#s=borowik…`, `#s=all…`) działają; rozmiar `lasy.pmtiles` rośnie nie więcej niż o 40% (pomiar w planie, §6).

## 2. Gatunki

### 2.1. Zmiany istniejących

- `rydz` → nazwa „Rydz mleczaj” (*Lactarius deliciosus*), partnerzy tylko `SO` (rydz pod świerkiem to osobny gatunek, §2.2). Klucz bez zmian (linki).
- `borowik` (*Boletus edulis*) — bez zmian: to gatunek o szerokim spektrum partnerów (sosna, świerk, buk, dąb). Borowik sosnowy dochodzi jako osobny gatunek, nakładający się z nim pod sosną; różni się siedliskiem (ubogie bory) i wcześniejszym sezonem.
- Pozostałe (`podgrzybek`, `kurka`, `kozlarz`, `maslak`) — bez zmian parametrów.

### 2.2. Nowe gatunki

Parametry startowe są eksperckie (literatura grzyboznawcza, ogólnodostępne atlasy); stroi je raport walidacji (spec H), dla rzadkich gatunków zostaną eksperckie. Kolumna „Siedlisko” używa zestawów z §2.3. Wiek: `min/opt` (lat), `max` tylko gdy podany. Temperatura gleby: trapez `[zero_low, opt_low, opt_high, zero_high]` °C. Opad: `rain_min/rain_full` mm (domyślnie 10/40).

| Klucz | Nazwa (łac.) | Grupa | Partnerzy | Wiek | Siedlisko preferowane / sąsiednie | Sezon | Temp. |
|---|---|---|---|---|---|---|---|
| `kozlarz_czerwony` | Koźlarz czerwony (*Leccinum aurantiacum*) | kozlarze | OS, TP | 10/20 | @lasy_mieszane_swieze, @lasy_swieze, @bory_mieszane_swieze, @lasy_mieszane_wilgotne / @lasy_wilgotne, @bory_mieszane_wilgotne | 06-15 – 10-31 | 6, 12, 20, 26 |
| `kozlarz_pomaranczowy` | Koźlarz pomarańczowożółty (*Leccinum versipelle*) | kozlarze | BRZ | 10/15 | @bory_wilgotne, @bory_mieszane_wilgotne, @bory_bagienne, @bory_mieszane_bagienne / @bory_ubogie, @bory_mieszane_swieze, @lasy_mieszane_wilgotne | 07-01 – 10-31 | 6, 12, 20, 26 |
| `kozlarz_grabowy` | Koźlarz grabowy (*Leccinum pseudoscabrum*) | kozlarze | GB | 15/25 | @lasy_swieze, @lasy_mieszane_swieze, @lasy_wilgotne / @lasy_mieszane_wilgotne, @bory_mieszane_swieze | 06-15 – 10-15 | 8, 13, 21, 27 |
| `kozlarz_debowy` | Koźlarz dębowy (*Leccinum quercinum*) | kozlarze | DB | 20/40 | @lasy_swieze, @lasy_mieszane_swieze, @bory_mieszane_swieze / @lasy_wilgotne, @lasy_mieszane_wilgotne | 07-01 – 09-30 | 8, 13, 21, 27 |
| `borowik_sosnowy` | Borowik sosnowy (*Boletus pinophilus*) | borowiki | SO | 30/50 | @bory_ubogie, @bory_mieszane_swieze / @bory_wilgotne, @bory_mieszane_wilgotne | 06-15 – 10-31 | 6, 12, 20, 26 |
| `borowik_usiatkowany` | Borowik usiatkowany (*Boletus reticulatus*) | borowiki | DB, BK, GB | 40/60 | @lasy_swieze, @lasy_mieszane_swieze / @bory_mieszane_swieze | 05-15 – 09-15 | 10, 15, 23, 28 |
| `podgrzybek_zajaczek` | Podgrzybek zajączek (*Xerocomus subtomentosus*) | podgrzybki | DB, BK, SO, SW | 20/30 | @bory_mieszane_swieze, @lasy_mieszane_swieze, @lasy_swieze / @bory_ubogie, @bory_mieszane_wilgotne, @lasy_mieszane_wilgotne | 06-15 – 10-31 | 6, 12, 20, 26 |
| `podgrzybek_zlotawy` | Podgrzybek złotawy (*Xerocomellus chrysenteron*) | podgrzybki | DB, BK, SO, SW, BRZ | 15/25 | @bory_mieszane_swieze, @lasy_mieszane_swieze, @lasy_swieze, @bory_ubogie / @bory_wilgotne, @bory_mieszane_wilgotne, @lasy_mieszane_wilgotne, @lasy_wilgotne | 06-15 – 11-15 | 5, 10, 19, 25 |
| `podgrzybek_czerwonawy` | Podgrzybek czerwonawy (*Hortiboletus rubellus*) | podgrzybki | DB | 20/40 | @lasy_swieze, @lasy_mieszane_swieze / @bory_mieszane_swieze | 07-01 – 09-30 | 10, 15, 23, 28 |
| `maslak_zolty` | Maślak żółty (*Suillus grevillei*) | maslaki | MD | 5/10 | @lasy_mieszane_swieze, @bory_mieszane_swieze, @lasy_swieze / @bory_ubogie, @lasy_mieszane_wilgotne, @bory_mieszane_wilgotne, @lasy_wilgotne | 07-01 – 10-31 | 4, 10, 18, 24 |
| `maslak_sitarz` | Maślak sitarz (*Suillus bovinus*) | maslaki | SO | 10/20, max 60 | @bory_ubogie / @bory_wilgotne, @bory_mieszane_swieze | 08-01 – 10-31 | 4, 10, 18, 24 |
| `rydz_swierkowy` | Rydz świerkowy (*Lactarius deterrimus*) | rydze | SW | 10/20, max 60 | @bory_mieszane_swieze, @lasy_mieszane_swieze, @lasy_swieze / @bory_mieszane_wilgotne, @lasy_mieszane_wilgotne, @bory_ubogie | 08-01 – 10-31 | 5, 10, 18, 24 |

`soil_moisture_min` dla wszystkich nowych: domyślne 0.15. Czynniki siedliska ze speców F i I: nowe gatunki dostają tabele domyślne (`factors_default`), z nadpisaniami: `kozlarz_pomaranczowy` jak `kozlarz` (tolerancja wilgotnych i bagiennych), `maslak_sitarz` jak `maslak`, `rydz_swierkowy` — `degr` pusta (jak `rydz`). Gdy F/I nie są jeszcze wdrożone, ten punkt wchodzi razem z nimi.

### 2.3. Zestawy siedlisk w `species.yaml`

Nowa sekcja najwyższego poziomu `habitat_sets`; element listy `preferred`/`adjacent` zaczynający się od `@` jest rozwijany przez `forecast/species.py` (nieznany zestaw → `ValueError`; kod występujący jednocześnie w `preferred` i `adjacent` po rozwinięciu → zostaje w `preferred`). Istniejące gatunki zostają przy jawnych listach (wynik `h` bez zmian).

```yaml
habitat_sets:
  bory_ubogie: [BS, BSW, BGSW]
  bory_wilgotne: [BW, BWG, BGW]
  bory_bagienne: [BB, BGB]
  bory_mieszane_swieze: [BMSW, BMGSW]
  bory_mieszane_wilgotne: [BMW, BMWYZ, BMWYZSW, BMWYZW, BMGW]
  bory_mieszane_bagienne: [BMB, BMGB]
  lasy_mieszane_swieze: [LMSW, LMGSW, LMWYZ, LMWYZSW, LMG]
  lasy_mieszane_wilgotne: [LMW, LMGW, LMWYZW]
  lasy_swieze: [LSW, LWYZS, LWYZSW, LWYZ, LGSW, LG]
  lasy_wilgotne: [LW, LWYZW, LGW]
```

Przypisanie kodów wyżynnych do zestawów odpowiada odpowiednikom ze specu E (`tests/test_habitat.py::test_upland_habitat_scores_like_lowland_analogue`): `BMWYZ ≙ BMW`, `BMWYZSW ≙ BMWYZ`, więc oba są w borach mieszanych wilgotnych.

`pipeline.species_info` tłumaczy rozwinięte kody (w `gatunki.json` zestawy nie występują).

### 2.4. Treści (`content/gatunki.yaml`)

Każdy nowy gatunek: `latin`, `wiki` (artykuł w polskiej Wikipedii), `description` (2–4 zdania: kapelusz, rurki/blaszki, trzon, miąższ i jego przebarwienie, gdzie rośnie) i `lookalikes` z ryzykiem. Sobowtóry obowiązkowe (bezpieczeństwo):

| Gatunek | Sobowtóry (ryzyko) |
|---|---|
| koźlarze (wszystkie 4 nowe) | goryczak żółciowy (*Tylopilus felleus*, niejadalny) |
| `borowik_sosnowy`, `borowik_usiatkowany` | goryczak żółciowy (niejadalny), borowik szatański (*Rubroboletus satanas*, trujący) |
| `podgrzybek_zajaczek`, `podgrzybek_zlotawy` | goryczak żółciowy (niejadalny), pieprzowiec pieprzowy (*Chalciporus piperatus*, niejadalny) |
| `podgrzybek_czerwonawy` | borowik szatański (trujący) |
| `maslak_zolty`, `maslak_sitarz` | pieprzowiec pieprzowy (*Chalciporus piperatus*, niejadalny) |
| `rydz_swierkowy` | mleczaj wełnianka (*Lactarius torminosus*, trujący), mleczaj omszony (*Lactarius pubescens*, trujący) |

Nowe nazwy kodów drzew w `codes.trees`: `OS` osika, `TP` topola, `GB` grab, `MD` modrzew. Flaga `reviewed: false` zostaje; nowe teksty są oznaczone w karcie jak dotychczasowe („opis niezweryfikowany”).

## 3. Grupy

- `species.yaml`: pole `group` (opcjonalne) przy gatunku: `borowiki` (`borowik`, `borowik_sosnowy`, `borowik_usiatkowany`), `kozlarze` (`kozlarz` + 4 nowe), `podgrzybki` (`podgrzybek` + 3 nowe), `maslaki` (`maslak`, `maslak_zolty`, `maslak_sitarz`), `rydze` (`rydz`, `rydz_swierkowy`). `kurka` bez grupy.
- `content/gatunki.yaml`: sekcja `groups` z tekstami UI: `borowiki: {name: "Borowiki", all: "Wszystkie borowiki"}`, `kozlarze: {name: "Koźlarze (kozaki)", all: "Wszystkie koźlarze"}`, `podgrzybki: {name: "Podgrzybki", all: "Wszystkie podgrzybki"}`, `maslaki: {name: "Maślaki", all: "Wszystkie maślaki"}`, `rydze: {name: "Rydze", all: "Wszystkie rydze"}`. Grupa z `species.yaml` bez tekstów (lub odwrotnie) → `ValueError` w `species_info`.
- `gatunki.json`: każdy gatunek dostaje `group` (klucz lub `null`); nowe pole najwyższego poziomu `groups: [{"key", "name", "all", "species": [...]}]` w kolejności pierwszego wystąpienia w `species.yaml`. Zmiana wstecznie zgodna.
- Kolejność gatunków w `species.yaml`: najpierw dotychczasowe 6 w obecnej kolejności, nowe dopisane na końcu — kolejność `index.species` w centroidach i atrybutów zostaje zgodna dla starych klientów.

## 4. Aplikacja

### 4.1. Wybór

- `<select id="species">`: „Wszystkie gatunki” (`all`), potem dla każdej grupy `<optgroup label="Koźlarze (kozaki)">` z pierwszą opcją „Wszystkie koźlarze” (`g-kozlarze`) i gatunkami grupy; na końcu `<optgroup label="Inne">` z gatunkami bez grupy (kurka).
- Hash: `s=g-<grupa>` (np. `#s=g-kozlarze`); nieznana wartość → domyślny gatunek jak dziś. `parseHash` dostaje listę dozwolonych wartości z wczytanego `gatunki.json`.
- Przycisk karty gatunku (ⓘ) wyłączony w trybie grupy i „wszystkie” (jak dziś dla `all`).

### 4.2. Jeden mechanizm dla „wszystkie” i grup

Wybór rozwiązywany jest do listy kluczy: gatunek → `[key]`, `all` → wszystkie gatunki, `g-x` → gatunki grupy. Tryb wielogatunkowy (dziś tylko `all`) działa na dowolnej liście:

- **mapa:** `fillColorExpression`/`fillOpacityExpression` w `web/js/map.js` dostają listę kluczy zamiast stałego `ALL_KEYS` (dziś zbudowanego z zaszytej listy `SPECIES`) — wynik = max po gatunkach z listy;
- **popup:** paski gatunków z listy (jak dziś w „wszystkie”), z najlepszym gatunkiem w nagłówku; trend i wykres liczone po liście;
- **ranking:** najlepszy gatunek z listy na wydzielenie, etykieta z krótką nazwą gatunku (jak dziś w `all`);
- **legenda, dzień, baner:** bez zmian.

Zaszyta lista `SPECIES` w `web/js/data.js` zostaje tylko jako awaryjna (brak `gatunki.json`) i jest aktualizowana do 18 gatunków; wszystkie miejsca, które dziś iterują `SPECIES` przy wczytanym `gatunki.json`, przechodzą na listę z pliku.

## 5. Pipeline i prognoza

- `build_tiles.compute_features` — bez zmian logiki (iteruje gatunki z `species.yaml`). Rozmiar: atrybut `h_<gatunek>` równy 0 jest pomijany w kafelkach (klient już traktuje brak jako 0: `["to-number", ["get", …], 0]`, `Number(props[…] ?? 0)`); plan sprawdza każde miejsce odczytu `h_*` w `web/js/` i testem potwierdza zachowanie dla brakującego atrybutu. `docs/data/api.md`: „brak atrybutu = 0”.
- Centroidy: wiersze dłuższe o 12 kolumn; próg „max h ≥ 40” bez zmian (więcej wydzieleń przejdzie próg — pomiar w planie).
- `forecast` — bez zmian kodu; `pogoda.json` rośnie ~3× (dziś ~0,6 MB przed gzip). Plan mierzy rozmiar po zmianie; jeśli > 2 MB przed gzip, `forecast/run.py` zaokrągla składowe do 2 miejsc (już jest) i pomija tablice składowych równe w całości 0 — decyzja w planie po pomiarze, z aktualizacją schematu i `api.md`.
- Walidacja (spec H): nowe gatunki wchodzą automatycznie (`latin` z treści).

## 6. Testy i pomiary

- `tests/test_species.py`: rozwijanie `@zestaw`, nieznany zestaw → błąd, kod w obu listach → `preferred`; 18 gatunków się ładuje; `rydz` ma partnerów `{SO}`.
- `tests/test_species_info.py`: `group` i `groups` w `gatunki.json`, brak tekstów grupy → błąd, nowe kody drzew przetłumaczone, kolejność gatunków (6 dotychczasowych na początku).
- `tests/test_habitat.py`: po jednym przypadku na nowy gatunek (np. 40-letnia osina na LMSW → wysoki `kozlarz_czerwony`, sosna na BSW → 0; modrzew → `maslak_zolty` > 0, sosna → 0).
- `tests/test_build_tiles.py`: `h_<gatunek> = 0` pominięty w cechach.
- `web/tests/`: `parseHash` z `g-kozlarze`; budowa `<select>` z optgroup; `fillColorExpression` dla listy kluczy; popup w trybie grupy (paski tylko gatunków grupy); ranking w trybie grupy; brak atrybutu `h_*` = 0 w każdym miejscu odczytu.
- Pomiary w planie (przed/po, zapisane w opisie commita): rozmiar `lasy.pmtiles`, `centroidy/`, `pogoda.json`; czas `pipeline.build`.
