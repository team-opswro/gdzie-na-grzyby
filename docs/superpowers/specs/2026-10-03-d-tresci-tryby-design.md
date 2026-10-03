# D. Treści i tryby — projekt

Data: 2026-10-03
Status: do przeglądu
Zakres: usprawnienia 9 (tryb „Wszystkie gatunki”), 11 (karta gatunku z sobowtórami), 13 („Jak to działa?”).
Powiązane: A (wykres w trybie all), B (ranking z najlepszym gatunkiem).
Kolejność wdrażania specyfikacji: **C → A → B → D** (C najpierw, bo dziś mapa może polecać rezerwaty);
każda jest samodzielna, zależności między nimi są miękkie (opisane w „Powiązane”).

## 1. Cel

Użytkownik, który nie wie, czego szukać, widzi najlepsze miejsca dla dowolnego gatunku; wie, jak
rozpoznać gatunek i czym go nie pomylić; rozumie, skąd bierze się wynik.

**Kryterium sukcesu:** opcja „Wszystkie gatunki” koloruje mapę maksimum po gatunkach; przycisk ⓘ
otwiera kartę gatunku z sezonem, siedliskami i sobowtórami; „Jak to działa?” wyjaśnia model
w kilku akapitach.

## 2. Tryb „Wszystkie gatunki” (9)

- Klucz `all`, pierwsza pozycja w selekcie („Wszystkie gatunki”), `s=all` w hashu, nadal
  domyślny `borowik`.
- `map.js`: dla `all` wynik = `["max", e_1, …, e_6]`, gdzie `e_k` to istniejące wyrażenie wyniku
  gatunku `k` (z własnym `weatherMatch`); gatunek bez pogody w komórce daje −1 i nie wygrywa.
  Wszystkie gatunki bez pogody → „brak danych”. Bez `pogoda` → `max` z `h_*`.
- `ranking.js`: dla `all` wynik wiersza = maksimum po gatunkach, zwracany dodatkowo `species`
  (klucz najlepszego). Wiersz: „72 · borowik”.
- Popup: lista gatunków posortowana malejąco po wyniku, każdy z paskiem (szerokość ∝ wynik,
  kolor klasy) i wynikiem; reszta popupu (A, B, C) dotyczy najlepszego gatunku. Wykres z A
  pokazuje maksimum na dzień; trend i szczyt w popupie `all` również liczone z maksimum na dzień.

## 3. Karta gatunku (11)

### 3.1. Dane
- Parametry zostają w `species.yaml` (bez zmian).
- Nowy `content/gatunki.yaml` (ręcznie pisany):

```yaml
reviewed: false          # true dopiero po przeglądzie przez osobę z wiedzą mykologiczną
codes:
  trees: {SO: sosna, SW: świerk, BK: buk, DB: dąb, BRZ: brzoza}
  habitats: {BSW: bór świeży, BMSW: bór mieszany świeży, ...}   # wszystkie kody z species.yaml
species:
  borowik:
    latin: Boletus edulis
    wiki: https://pl.wikipedia.org/wiki/Borowik_szlachetny
    description: "…2–4 zdania o rozpoznawaniu…"
    lookalikes:
      - {name: Goryczak żółciowy, latin: Tylopilus felleus, risk: niejadalny, how: "…"}
```

  `risk ∈ {niejadalny, trujący, śmiertelnie trujący}`. Wstępne sobowtóry: borowik — goryczak
  żółciowy, borowik szatański; podgrzybek — goryczak żółciowy; koźlarz — goryczak żółciowy;
  kurka — lisówka pomarańczowa; rydz — mleczaj wełnianka; maślak — brak groźnych (krótka uwaga).
- Nowy `pipeline/species_info.py` (`python -m pipeline.species_info`): scala `species.yaml` +
  `content/gatunki.yaml` → `web/data/gatunki.json` (lista w kolejności z `species.yaml`, z polami
  `key, name, latin, season, partners[], habitats_preferred[], habitats_adjacent[], age_min,
  description, lookalikes[], wiki`, oraz `reviewed`). Brak tłumaczenia kodu → błąd.
- Test pilnuje aktualności: wygenerowany plik = commitowany `web/data/gatunki.json`.

### 3.2. Frontend
- `data.js`: lista gatunków z `gatunki.json`; obecna stała `SPECIES` zostaje jako fallback, gdy
  pliku brak. `gatunki.json` ładowany przed `parseHash` (mały plik); `parseHash` dostaje listę kluczy.
- Przycisk ⓘ obok selecta (dla `all` nieaktywny) otwiera `<dialog id="species-card">`:
  nazwa + łacińska, sezon („1 lip – 31 paź”), drzewa partnerskie, siedliska (preferowane / sąsiednie),
  minimalny wiek drzewostanu, opis, sekcja „Nie pomyl z” (nazwa, łacińska, etykieta ryzyka
  w kolorze: niejadalny żółty, trujący pomarańczowy, śmiertelnie trujący czerwony, opis różnic),
  link do Wikipedii.
- Stały disclaimer na dole karty: „Nie zbieraj grzybów, których nie znasz. W razie wątpliwości
  skorzystaj z punktu grzyboznawczego (Sanepid).”
- `reviewed: false` → dodatkowo „Opis nie został jeszcze zweryfikowany przez grzyboznawcę.”
- Brak zdjęć (licencje).

## 4. „Jak to działa?” (13)

- Link „Jak to działa?” w stopce i przycisk „?” w topbarze otwierają `<dialog id="about">`.
- Treść statyczna w `index.html`:
  1. Wynik = siedlisko × pogoda (0–100); klasy kolorów.
  2. Siedlisko: gatunek panujący, wiek, typ siedliskowy z BDL — liczone raz na sezon.
  3. Pogoda: deszcz sprzed 5–21 dni (najważniejsze 7–14), temperatura gleby z ostatnich 5 dni,
     wilgotność gleby, sezon gatunku; odświeżana o 5:00 i 14:00.
  4. Ograniczenia: model heurystyczny bez kalibracji, tylko lasy Lasów Państwowych, BDL nie zna
     gatunków domieszkowych, prognoza pogody bywa błędna.
  5. Źródła i licencje (jak w stopce).
- Dynamicznie: „Prognoza z: <generated_at w czasie lokalnym>” lub „brak prognozy”.
- Okno nie otwiera się samo.

## 5. Testy

- pytest `tests/test_species_info.py`: scalenie, tłumaczenie kodów, błąd przy brakującym kodzie,
  aktualność `web/data/gatunki.json`.
- node `map.test.js`: wyrażenie `max` dla `all` (z pogodą, bez pogody, część gatunków bez danych).
- node `ranking.test.js`: `all` — wynik i `species` najlepszego.
- node `hash.test.js`: `s=all`, lista kluczy z `gatunki.json`.
- node `data.test.js`: fallback listy gatunków bez `gatunki.json`.

## 6. Poza zakresem
Zdjęcia gatunków, nowe gatunki, onboarding przy pierwszej wizycie, tłumaczenia.
