# N. Analiza aplikacji i propozycje nowych funkcji

Data: 2026-10-04. Status: **propozycje do wyboru** — nic z tej listy nie jest wdrażane przed akceptacją
(zasada: analiza → wybór → spec → akceptacja → plan → wykonanie). Po wyborze każda pozycja (lub paczka) dostaje
własny spec.

## Stan (co już jest)

Mapa wydzieleń z wynikiem `h × w` dla 18 gatunków w grupach i trybu „Wszystkie”; 8 dni (wczoraj + 6 w przód),
popup z wykresem tygodnia, trendem, składowymi modelu, czynnikami siedliska i wilgotnością miejsca; ranking
top 10 w promieniu (od środka mapy lub lokalizacji) z nawigacją (Google/OSM); rezerwaty, parkingi OSM, dwa podkłady;
karty gatunków; udostępnianie linku z hashem; PWA z pracą offline; dane wersjonowane w R2, prognoza 2× dziennie.
Model: siedlisko z BDL + teren + wilgotność miejsca (L), pogoda z bilansem wody podłoża (M), walidacja na GBIF (H).

Odłożone wcześniej (z sekcji „poza zakresem” specyfikacji A–L): zgłaszanie znalezisk (backend), najbliższa
miejscowość, Natura 2000/parki, zdjęcia gatunków, onboarding, LiDAR, „bez tłumów”, iNaturalist jako źródło.

## Obserwacje z analizy

1. **Pętla „teren → model” działa tylko przez rozmowę.** Zgłoszenie z 4.10 dało dwa specy (L, M), ale aplikacja
   nie pozwala zapisać, gdzie się było i co się znalazło, ani odtworzyć, co mapa pokazywała tamtego dnia
   (`live/pogoda.json` jest nadpisywany).
2. **Aplikacja odpowiada „gdzie”, słabiej „kiedy”.** Dane na 6 dni w przód są, ale żeby znaleźć najlepszy dzień,
   trzeba klikać strzałkami dzień po dniu; ranking liczy jeden dzień.
3. **Pogoda jest niewidoczna przestrzennie.** Kratka 0,1° decyduje o `w`, ale nie widać, gdzie popadało, a gdzie
   przesycha (po specu M to główny czynnik w suszy).
4. **Dojście do miejsca.** Parkingi są na mapie, ale ranking ich nie uwzględnia — miejsce 400 m od parkingu
   i 3 km w głąb lasu wyglądają tak samo.
5. **Jedna pojemność wody dla wszystkich gleb** (ryzyko z M): piaski borowe przesychają 2–3× szybciej niż gliny.
6. **Rozmiar `pogoda.json`:** po M ≈ 270 KB gzip (+21%); `moist` nie zależy od gatunku, a jest powielony 18×.
7. Stopka „Model heurystyczny, bez kalibracji” jest nieaktualna — model jest walidowany na GBIF (porównawczo).

## Propozycje

Koszt: S ≈ wieczór, M ≈ 1–2 dni pracy agenta, L ≈ wiele dni / przebudowa danych.

| # | Propozycja | Wartość | Koszt | Zależności |
|---|---|---|---|---|
| 1 | **„Kiedy jechać?”** — najlepszy dzień tygodnia | wysoka | S | — |
| 2 | **Warstwa „wilgotność podłoża”** (kratki z `wx.water`) | średnia–wysoka | S | M |
| 3 | **Odchudzenie `pogoda.json`** (`moist` per kratka) + stopka | techniczna | S | M |
| 4 | **Dziennik wypraw** (lokalny, z eksportem) | wysoka dla modelu | M | 5 (opcjonalnie) |
| 5 | **Archiwum prognoz** w R2 | średnia | S | — |
| 6 | **Dojście: odległość do parkingu** w rankingu i filtr | średnia–wysoka | M | przebudowa centroidów |
| 7 | **Pojemność wody per gleba** (2–3 klasy) | średnia (model) | M–L | M, przebudowa kafelków |
| 8 | **„Co się zmieniło od ostatniej wizyty”** (bez push) | średnia | S–M | — |

### 1. „Kiedy jechać?” — najlepszy dzień tygodnia

- Popup: pod wykresem „Najlepiej: czwartek (62)” — maksimum wyniku z dni dziś…+6 (dane już są w `chartData`).
- Ranking: przełącznik „dziś / najlepszy dzień tygodnia”; w drugim trybie wynik wiersza = max po dniach,
  w `line2` dopisek dnia („czw.”). Hash: `r=best`.
- Bez zmian w danych. Testy: `ranking.test.js` (max po dniach, remis → wcześniejszy dzień), `popup.test.js`.

### 2. Warstwa „wilgotność podłoża”

- Przełącznik obok podkładów: półprzezroczyste kratki 0,1° kolorowane `wx.water` wybranego dnia
  (5 klas od „przesuszone” do „pełny zapas”), etykieta „bez deszczu od N dni” w popupie kratki.
- Geometria kratek liczona w kliencie z `grid.json` (już publikowany) — bez nowych plików.
- Pomaga zrozumieć, dlaczego wynik spadł, i szukać miejsc, gdzie niedawno popadało.

### 3. Odchudzenie `pogoda.json` i drobne

- `moist` → `wx[cell].moist` (jedna seria na kratkę zamiast 18); klient czyta z `wx`, a gdy brak — z gatunku
  (zgodność z plikiem z M). ≈ −45 KB gzip na każde pobranie.
- Stopka: „Model heurystyczny, sprawdzany na obserwacjach GBIF” (lub usunąć zdanie — decyzja użytkownika).

### 4. Dziennik wypraw (lokalny)

- W popupie wydzielenia: „Byłem tu dziś: pusto / trochę / dużo” (+ opcjonalnie gatunek, notatka).
- Zapis w `localStorage`/IndexedDB urządzenia (bez backendu, bez kont); warstwa „moje wyprawy” (znaczniki
  w kolorach oceny); lista z możliwością usunięcia.
- Eksport GeoJSON (Udostępnij/Pobierz) → `scripts/field_reports.py` porównuje wpisy z modelem (pogoda
  historyczna z Open-Meteo jak w walidacji) i wypisuje rozbieżności — materiał do kolejnych kalibracji
  zamiast opisu w rozmowie.
- Ryzyko: dane tylko na jednym urządzeniu (świadomie, prywatność miejscówek).

### 5. Archiwum prognoz

- `forecast` przy wysyłce zapisuje też `hist/pogoda-YYYY-MM-DD.json` (pierwszy przebieg dnia), retencja 60 dni.
- Użycie: odtworzenie mapy z dnia wyprawy (dla zgłoszeń z terenu i dziennika), później „ostatnie 2 tygodnie”
  w wykresie popupu.
- Koszt R2 pomijalny (≈ 270 KB × 60).

### 6. Dojście: odległość do parkingu

- `pipeline`: dla wydzielenia odległość od centroidu do najbliższego parkingu OSM (metry, zaokrąglone do 100 m)
  jako kolumna `extra` w centroidach i atrybut `park` w kafelkach.
- Ranking: dopisek „parking 400 m”; filtr „do 1 km od parkingu” (select obok promienia).
- Wymaga przebudowy danych i publikacji (kolejność: web → publish, jak w v2).

### 7. Pojemność wody per gleba

- Forecast liczy wiadro dla 2–3 klas (`C` = 20 mm piaski/BS–BMSW, 35 mm gliny/lasy, 50 mm gleby organiczne/
  bagienne) → `wx[cell].moist_<klasa>`; wydzielenie ma atrybut `wc` (klasa z typu siedliskowego i gleby BDL).
- Klient wybiera serię wg `wc` — wynik różni się w obrębie kratki tam, gdzie dziś różni się tylko `wet`.
- Wymaga walidacji GBIF (bezpiecznik jak w M) i przebudowy kafelków.

### 8. „Co się zmieniło od ostatniej wizyty”

- Przy otwarciu PWA porównanie z ostatnio oglądanym stanem (zapisanym lokalnie): „W Twojej okolicy (20 km)
  od wtorku: 12 miejsc przeszło na »dobrze«”. Bez Web Push (który wymaga backendu subskrypcji).

## Rekomendacja

1. Paczka **1 + 2 + 3** (jeden spec, wszystko S, bez przebudowy danych) — największa wartość dla grzybiarza
   od ręki, kontynuacja M.
2. Potem **5 + 4** (pętla zgłoszeń z terenu) — usprawnia kolejne kalibracje.
3. **6** przy najbliższej przebudowie danych; **7** po zebraniu kilku wpisów z dziennika (żeby było na czym sprawdzić).
4. **8** opcjonalnie.

Pytania do decyzji: którą paczkę bierzemy; czy dziennik ma zbierać gatunek; czy zmieniać zdanie w stopce.
