# M. Bilans wodny podłoża: impuls deszczu × bieżąca wilgotność — projekt

Data: 2026-10-04. Status: podejście i rola `wet_adjust` zaakceptowane w rozmowie; spec, plan i wykonanie
samodzielne (użytkownik nieobecny, autoryzował pracę nocną). Kryterium kalibracji wybrane przez użytkownika:
**fizyka i literatura, walidacja GBIF tylko jako bezpiecznik**.

## Problem

Zgłoszenie z terenu 2026-10-04 (spec L): kratka `505_176` (50,55° N, 17,65° E), w terenie wyraźnie sucho,
a model dał `w` = 0,80 (`rain` 0,80, pozostałe składowe 1,0). Rozkład danych Open-Meteo z tego dnia:

| | |
|---|---|
| opad w oknie 5–21 dni wstecz | 41,3 mm, z czego 21,3 mm 20.09 (14 dni wcześniej) i 9,8 mm 24.09 |
| ostatni deszcz | 24.09 — potem 10 dni bez opadu, ET0 ≈ 2,5 mm/dzień |
| bilans ważony (`water`) | 33,9 mm; ET0 z `ET_ALPHA` = 0,15 odjęło ≈ 5 mm z ≈ 34 mm |
| wilgotność gleby 3–27 cm | 0,23–0,25, malejąca; próg kary `soil_moisture_min` = 0,15 — kara nie zadziałała |

Przyczyny:

1. Okno 5–21 dni nie widzi ostatnich 4 dni, a 5–6 dni liczy z wagą 0,5. Model pamięta deszcz sprzed 1–2 tygodni
   (ekologicznie słusznie: wyzwalacz owocnikowania), ale nie wie, że od tamtej pory wszystko przeschło.
2. `ET_ALPHA` = 0,15 to ułamek parowania — strojony na GBIF, nie na fizyce.
3. Kara z wilgotności Open-Meteo jest praktycznie martwa: modelowa wilgotność (ICON, gleba nie-borowa) rzadko
   spada poniżej 0,15 m³/m³, a w piaskach borowych realna woda dostępna jest dużo niższa.

## Cel i kryteria sukcesu

Rozdzielić dwa warunki owocnikowania: **impuls** (był deszcz 1–3 tygodnie temu) i **wilgotne podłoże teraz**.

- Przypadek 4.10 w `505_176`: `w` wyraźnie spada (cel ≤ 0,5), czynnik ograniczający „przesuszone podłoże”.
- Przy deszczowym okresie (podłoże pełne) wynik bez zmian względem dzisiejszego modelu z `ET_ALPHA` = 0.
- Bezpiecznik: AUC `w` w walidacji GBIF (borowik 0,569, podgrzybek 0,594 — `pipeline/data/walidacja-m-baza`)
  nie spada o więcej niż 0,01 dla żadnego z dwóch gatunków. Parametrów nie optymalizujemy na GBIF.
- Prognoza: kilka suchych, ciepłych dni w przód obniża `w` w kolejnych dniach (bilans liczony także na prognozie).

## Projekt

### 1. Składowa `moist` — wiadro wierzchniej warstwy (FAO-56, jednowarstwowy bilans)

Dla dnia `i` liczony jest zapas wody `S` w warstwie korzeniowo-ściółkowej o pojemności `C` (mm):

```
S_0 = C                                      # start serii (prognoza: 30 dni wstecz; walidacja: 10 kwietnia)
S_j = min(C, max(0, S_{j−1} + P_j − KC · ET0_j))    dla j = 0 … i−1
f   = S / C                                   # zapas względny w dniu i (stan na początek dnia)
moist = MOIST_FLOOR + (1 − MOIST_FLOOR) · clamp((f − MOIST_LOW) / (MOIST_HIGH − MOIST_LOW), 0, 1)
```

Parametry (stałe w `forecast/model.py`, wspólne dla gatunków — jak `ET_ALPHA` dziś):

| stała | wartość | uzasadnienie |
|---|---|---|
| `BUCKET_MM` (`C`) | 25 | dostępna woda (θFC − θWP ≈ 0,05–0,11) piasków i piasków gliniastych w warstwie ~25 cm (FAO-56, tab. 19) ≈ 12–28 mm + warstwa organiczna |
| `BUCKET_KC` | 0,8 | ewapotranspiracja drzewostanu iglastego w sezonie ≈ 0,7–0,9 ET0; wierzchnia warstwa traci wodę przez parowanie i pobór korzeni |
| `MOIST_LOW` | 0,1 | poniżej ~10% zapasu podłoże przesuszone |
| `MOIST_HIGH` | 0,7 | od 70% zapasu bez ograniczeń: owocnikowanie wymaga podłoża bliskiego polowej pojemności wodnej, więc próg jest ostrzejszy niż próg stresu drzew z FAO-56 (wyczerpanie ~50% TAW, p ≈ 0,5) |
| `MOIST_FLOOR` | 0,1 | nie zero: przy wilgotnych miejscach (`wet`) korekta spec L musi móc podnieść wynik w suszy |

Zachowanie na przypadku 4.10 (prototyp na danych Open-Meteo): `rain` (bez `ET_ALPHA`) = 0,91, `f` = 0,33,
`moist` = 0,44, `w` ≈ 0,40.

Wrażliwość na przypadku 4.10 (`w`): `C` 20/25/30 mm przy `KC` 0,8 → 0,17/0,40/0,55; `KC` 0,7/0,8/0,9 przy
`C` 25 → 0,52/0,40/0,29. Przy `MOIST_HIGH` = 0,5 byłoby 0,56 — dlatego próg owocnikowania 0,7.

Brak `et0` w serii (stare dane / brak zmiennej) → `moist` = 1,0 (neutralnie).

### 2. Co znika

- `ET_ALPHA` → 0: `rain` wraca do roli czystego impulsu opadu (ważona suma 5–21 dni). Parowanie liczy wiadro.
  Funkcja `water()` zostaje (z `ET_ALPHA` = 0, by nie zmieniać kontraktu), stała z komentarzem.
- Kara z wilgotności Open-Meteo (`MOISTURE_PENALTY`, `soil_moisture_eff`, `soil_moisture_min` w `species.yaml`
  i `Species`) — usunięta; jej rolę przejmuje `moist`. `soil_m`/`soil_m_deep` w `wx` zostają jako diagnostyka.

### 3. Mnożnik i czynnik ograniczający

```
w = min(1, rain × moist × temp × season × pulse × frost)
```

`limiting_factor`: nowa kandydatka `moist` (kolejność remisu: season, frost, temp, moist, rain), kod
`dry_soil` (istniejący w kontrakcie; nowe znaczenie: „przesuszone podłoże — od ostatniego deszczu ubyło wody”).
`dry` = za mało deszczu w oknie impulsu.

### 4. Wilgotność miejsca (spec L) liczona z `moist`

`w_eff = min(1, w · moist^(γ−1))` — miarą suszy jest `moist` zamiast `rain`. Wilgotne miejsce wypada lepiej,
gdy podłoże przesycha, a nie gdy po prostu dawno nie padało. Po stronie klienta (`web/js/data.js`, `web/js/map.js`):
`moist` z `pogoda.json`, a gdy go brak (stary plik sprzed pierwszego przebiegu nowego forecastu) — `rain` jak dziś.
`pipeline/validate.py` (`wet_eval`): `adjust(c.w, c.moist, wet)`, dzień „suchy” = `moist < 0,8`.

### 5. Kontrakt `pogoda.json` (zgodny wstecz)

- `cells[cell][gatunek].moist` — seria 0–1 (opcjonalna w schemacie, forecast zawsze ją zapisuje).
- `wx[cell].water` — zapas względny `f` (0–1, 2 miejsca), `wx[cell].dry_days` — dni od ostatniego dnia
  z opadem ≥ 1 mm (liczba całkowita ≥ 0, liczona do dnia `i−1`; limit 30 = cała historia serii). Oba opcjonalne.
- Stary klient: ignoruje nowe pola, liczy `wet_adjust` z `rain` — działa, tylko bez nowej korekty.
- `docs/data/api.md` — opis pól i zmiany znaczenia `dry_soil`.

### 6. Aplikacja

- Popup, sekcja pogody: wiersz „Zapas wody w podłożu: 35% · bez deszczu od 10 dni” (z `wx.water`, `wx.dry_days`;
  „bez deszczu od N dni” tylko dla N ≥ 3); wiersz „Parowanie” zostaje.
- „Szczegóły modelu”: wiersz „Wilgotność podłoża” = `pct(moist)`.
- `LIM_TEXT.dry_soil` = „Ogranicza: przesuszone podłoże”.
- `web/index.html`: opis modelu pogody — deszcz sprzed 5–21 dni jako impuls, bilans wody (opad − parowanie) jako
  wilgotność podłoża teraz; usunąć „pomniejszony o parowanie” i „wilgotność gleby (płytszej i głębszej warstwy)”.

## Testy

- `tests/test_model.py`: wiadro (pełne po deszczu, opróżnianie przy ET0, ograniczenie do [0, C]), `moist`
  (próg, podłoga, brak et0 → 1), `limiting_factor` zwraca `dry_soil` dla niskiego `moist`, przypadek 4.10 jako
  fikstura serii (`tests/fixtures/m_case_505_176.json`, dane z Open-Meteo) → `w` ≤ 0,5 i `lim` = `dry_soil`.
- `tests/test_run.py`: `moist`, `water`, `dry_days` w wyjściu i zgodność ze schematem.
- `tests/test_species.py`: brak `soil_moisture_min`.
- JS: `data.test.js` (`weatherFor` używa `moist`, fallback `rain`), `map.test.js` (wyrażenie z `moist`),
  `popup.test.js` (wiersz zapasu, tekst `dry_soil`).
- Walidacja GBIF przed/po (`--compare pipeline/data/walidacja-m-baza/walidacja.json`) — wynik w „Decyzjach po walidacji”.

## Ryzyka

- Opad Open-Meteo z siatki 0,1° nie trafia w lokalne burze — wiadro dziedziczy ten błąd (jak dziś impuls).
- Start serii z pełnym wiadrem zawyża zapas po długiej suszy sprzed 30 dni; wiadro 25 mm opróżnia się
  w ≈ 12 dni przy ET0 2,5 mm, więc wpływ na dzień „dziś” jest mały.
- Wynik jest wrażliwy na `C` i `KC` (tabela wrażliwości w §1) — wartości z literatury, nie dopasowane do jednego dnia.
- Jedna pojemność dla wszystkich gleb: piaski borowe i gliny lasów liściastych różnią się 2–3×. Ewentualna
  pojemność per siedlisko to osobny temat (wymagałaby `w` per wydzielenie, nie per kratka).

## Wydanie

Tylko `forecast` + `web` (bez przebudowy danych). Kolejność nieistotna: nowy klient obsługuje stary plik, stary klient
nowy plik. Coolify wdraża z `main`; nowy `pogoda.json` pojawi się po najbliższym przebiegu crona (05:00/14:00).

## Decyzje po walidacji

Walidacja GBIF (`pipeline/data/walidacja-m`, porównanie z `walidacja-m-baza`; borowik n = 90 dni, podgrzybek n = 52):

| | przed (L) | po (M) |
|---|---|---|
| AUC `w` borowik | 0,569 | 0,565 (−0,004 — w granicy bezpiecznika 0,01) |
| AUC `w` podgrzybek | 0,594 | 0,627 (+0,033); sama składowa `moist` 0,622 |
| AUC h·w_eff (wilgotność miejsca) borowik / podgrzybek | 0,539 / 0,614 | 0,552 / 0,619 |

Wrażliwość AUC `w` (borowik / podgrzybek) w zakresie z literatury — bez strojenia, tylko sprawdzenie odporności:
`C` 20 → 0,552 / 0,629; `C` 30 → 0,573 / 0,629; `KC` 0,7 → 0,570 / 0,626; `KC` 0,9 → 0,558 / 0,623.
Zysk podgrzybka stały, borowik ±0,01 wokół bazy — zostają wartości z literatury (`C` 25 mm, `KC` 0,8).

Przypadek 4.10 (`scripts/check_wet_case.py`, wynik dnia bez → z wilgotnością miejsca):

| | przed (L) | po (M) |
|---|---|---|
| podgrzybek, 379-b (suchy pagórek, pusto) | 56 → 40 | 28 → 8 |
| podgrzybek, 370-a (brzeg stawu, pełny koszyk) | 50 → 58 | 25 → 41 |
| borowik, 379-b / 370-a | 51 / 54 | 24 / 39 |

`w` = 0,40 (`rain` 0,91, `moist` 0,44, 9 dni bez deszczu), czynnik ograniczający `dry_soil`. Kolejność miejsc
zgodna z terenem i wyraźnie rozdzielona; pagórek spada do „słabo/brak”.

Uwaga: `MOIST_HIGH` = 0,7 wybrano przy znajomości przypadku 4.10 (przy 0,5 `w` = 0,56) — uzasadnienie fizyczne
w §1, ale to jedyny parametr, przy którym przypadek wpłynął na wybór.

### Zmiana 2026-10-05: `MOIST_HIGH` 0,7 → 0,5

Po wdrożeniu, w trwającej suszy, mapa była prawie w całości „brak” (5.10, podgrzybek: mediana `w` 0,12, maksimum 0,55;
nigdzie „bardzo dobrze”). Próg 0,7 był jedynym parametrem dobranym przy znajomości przypadku 4.10 — wracamy do wartości
z literatury (FAO-56, p ≈ 0,5). Walidacja GBIF praktycznie bez zmian:

| `MOIST_HIGH` | AUC `w` borowik / podgrzybek | h·w_eff borowik / podgrzybek | 4.10: `w` | 5.10 podgrzybek: p50 / p90 / max |
|---|---|---|---|---|
| 0,7 | 0,565 / 0,627 | 0,552 / 0,619 | 0,40 | 0,12 / 0,37 / 0,55 |
| 0,6 | 0,566 / 0,625 | 0,553 / 0,617 | 0,46 | 0,14 / 0,43 / 0,65 |
| **0,5** | 0,568 / 0,624 | 0,554 / 0,616 | 0,56 | 0,16 / 0,52 / 0,78 |

Przypadek 4.10 (podgrzybek, wynik z wilgotnością miejsca): pagórek 379-b 18 („słabo”), brzeg stawu 370-a 47 („dobrze”) —
kolejność i rozdzielenie zgodne z terenem; stary model: 40 / 58.
