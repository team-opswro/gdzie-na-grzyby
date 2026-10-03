# D. Treści i tryby — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tryb „Wszystkie gatunki” (maksimum po gatunkach na mapie, w rankingu i popupie), karta gatunku z sezonem, siedliskami i sobowtórami oraz okno „Jak to działa?”.

**Architecture:** Teksty w `content/gatunki.yaml`; `pipeline/species_info.py` scala je z `species.yaml` do `web/data/gatunki.json` (test pilnuje aktualności). Frontend czyta listę gatunków z `gatunki.json` (fallback: stała `SPECIES`), `map.js`/`ranking.js`/`chart.js` obsługują klucz `all`, `ui.js` dodaje dwa `<dialog>`.

**Tech Stack:** Python 3 (PyYAML, pytest), ES modules, `node:test`, MapLibre GL JS.

**Spec:** `docs/superpowers/specs/2026-10-03-d-tresci-tryby-design.md`

## Global Constraints

- Klucz trybu: `all`, etykieta „Wszystkie gatunki”, pierwsza pozycja selecta; `s=all` w hashu; domyślny gatunek nadal `borowik`.
- Wynik `all` = maksimum `round(h_k × w_k)` po gatunkach; gatunek bez pogody w komórce nie wygrywa; wszystkie bez pogody → „brak danych”; bez pliku pogody → maksimum `h_k`. Rezerwaty (`rez`) jak dotąd (szare).
- Ranking `all`: wynik wiersza/oddziału = maksimum, grupa ma dodatkowo `species` (klucz najlepszego); wiersz pokazuje „· <nazwa krótka gatunku>” (np. „· borowik”).
- Popup `all`: lista gatunków malejąco po wyniku, każdy z paskiem (szerokość ∝ wynik, kolor klasy) i liczbą; wynik, `lim`, wiersze `wx`, trend — dla najlepszego gatunku danego dnia; wykres = maksimum na dzień.
- `content/gatunki.yaml`: `reviewed: false`, `codes.trees` (`SO: sosna, SW: świerk, BK: buk, DB: dąb, BRZ: brzoza`), `codes.habitats` (wszystkie kody z `species.yaml`, nazwy pełne, np. `BSW: bór świeży`, `BMSW: bór mieszany świeży`, `LMWYZ: las mieszany wyżynny świeży`, `LMWYZW: las mieszany wyżynny wilgotny`, `BGSW: bór górski świeży`, `LGSW: las górski świeży`), `species.<klucz>`: `latin`, `wiki`, `description` (2–4 zdania), `lookalikes[]` (`name`, `latin`, `risk ∈ {niejadalny, trujący, śmiertelnie trujący}`, `how`).
- Sobowtóry (minimum): borowik — goryczak żółciowy (*Tylopilus felleus*, niejadalny: rurki różowieją, ciemna siateczka na trzonie, gorzki), borowik szatański (*Rubroboletus satanas*, trujący: czerwone pory i trzon, sinieje, pod dębami i bukami na glebach wapiennych); podgrzybek — goryczak żółciowy; koźlarz — goryczak żółciowy; kurka — lisówka pomarańczowa (*Hygrophoropsis aurantiaca*, niejadalna: prawdziwe, gęste, rozwidlone blaszki, miękki miąższ); rydz — mleczaj wełnianka (*Lactarius torminosus*, trujący: białe, ostre mleczko, kosmaty brzeg kapelusza; rydz ma pomarańczowe mleczko); maślak — `lookalikes: []` i zdanie w opisie, że w Polsce nie ma groźnych sobowtórów wśród maślaków.
- Łacina gatunków: borowik *Boletus edulis*, podgrzybek *Imleria badia*, kurka *Cantharellus cibarius*, koźlarz babka *Leccinum scabrum*, maślak *Suillus luteus*, rydz *Lactarius deliciosus*; `wiki` = artykuł polskiej Wikipedii.
- `web/data/gatunki.json`: `{ "reviewed": bool, "species": [ { key, name, latin, season: {start, end}, partners: [nazwy], habitats_preferred: [nazwy], habitats_adjacent: [nazwy], age_min, description, lookalikes, wiki } ] }` w kolejności `species.yaml`; brak tłumaczenia kodu → błąd.
- Karta (`<dialog id="species-card">`): nazwa + łacina, sezon („1 lip – 31 paź”), drzewa, siedliska (preferowane / sąsiednie), minimalny wiek drzewostanu („od 30 lat”), opis, „Nie pomyl z” (etykieta ryzyka: niejadalny żółty, trujący pomarańczowy, śmiertelnie trujący czerwony), link do Wikipedii; disclaimer: „Nie zbieraj grzybów, których nie znasz. W razie wątpliwości skorzystaj z punktu grzyboznawczego (Sanepid).”; przy `reviewed: false`: „Opis nie został jeszcze zweryfikowany przez grzyboznawcę.”
- „Jak to działa?” (`<dialog id="about">`): treść statyczna wg spec §4 (5 punktów) + „Prognoza z: <generated_at lokalnie>” lub „brak prognozy”. Otwierany linkiem „Jak to działa?” w stopce i w legendzie. Okno nie otwiera się samo.
- Przycisk ⓘ obok selecta (dla `all` `disabled`). Topbar mieści się w 375 px.
- Testy: `.venv/bin/pytest -q`, `node --test web/tests/*.test.js`.

## Review Focus

- Brak `gatunki.json` (404) → lista gatunków z fallbacku, karta pokazuje „Brak opisu gatunku”, mapa działa → test w Task 2.
- `s=all` z linku przy starym `pogoda.json` (bez `lim`/`wx`) → popup z listą gatunków i procentami, bez wyjątku → test w Task 3.
- Gatunek bez danych pogodowych w komórce w trybie `all` → pomijany przy maksimum; wszystkie bez danych → `null` → test w Task 3.
- Dialog na telefonie: zamykanie przyciskiem i klawiszem Esc, przewijanie długiej treści → weryfikacja w Task 5.
- Zmiana `species.yaml` bez przebudowy `gatunki.json` → test aktualności pada → test w Task 1.

---

### Task 1: Treści gatunków i `gatunki.json`

**Files:** Create `content/gatunki.yaml`, `pipeline/species_info.py`, `tests/test_species_info.py`, `web/data/gatunki.json`; Modify `README.md` (krok po `fetch_names`).

**Interfaces — Produces:** `build_info(species_yaml: dict, content: dict) -> dict` (format z Global Constraints); `format_season(mmdd_start, mmdd_end) -> str` („1 lip – 31 paź”, skróty miesięcy: sty, lut, mar, kwi, maj, cze, lip, sie, wrz, paź, lis, gru); CLI `python -m pipeline.species_info [--out web/data/gatunki.json]`.

- [ ] **Step 1: Failing tests:** `build_info` tłumaczy kody (`SO` → „sosna”), zachowuje kolejność `species.yaml`; brak kodu w `codes` → `KeyError`/`ValueError` z nazwą kodu; `format_season("07-01","10-31") == "1 lip – 31 paź"`; **aktualność**: `build_info(load(species.yaml), load(content/gatunki.yaml))` == zawartość `web/data/gatunki.json`.
- [ ] **Step 2–4:** FAIL → napisz `content/gatunki.yaml` (Global Constraints; teksty po polsku, rzeczowe) i moduł → wygeneruj plik → PASS.
- [ ] **Step 5:** Commit `feat: treści gatunków i gatunki.json`.

---

### Task 2: Lista gatunków z `gatunki.json` i `s=all`

**Files:** Modify `web/js/data.js`, `web/js/hash.js`; Tests `web/tests/data.test.js`, `web/tests/hash.test.js`

**Interfaces — Produces:** `ALL = "all"`; `loadSpecies(base = "data/") -> Promise<{ list: [{key, name, ...}], info: object|null }>` (fallback: `SPECIES` i `info: null`); `parseHash(hash, keys = SPECIES.map(k).concat(ALL))` — gatunek walidowany względem `keys`.

- [ ] **Step 1: Failing tests:** `loadSpecies` z mockiem fetch → lista z pliku; 404/wyjątek → `SPECIES`, `info null`; `parseHash("#s=all")` → `all`; `parseHash("#s=all", ["borowik"])` → `borowik`.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Commit `feat(web): lista gatunków z gatunki.json, klucz all w hashu`.

---

### Task 3: Tryb `all` — mapa, ranking, wykres, trend

**Files:** Modify `web/js/map.js`, `web/js/ranking.js`, `web/js/chart.js`, `web/js/data.js`; Tests `web/tests/map.test.js`, `ranking.test.js`, `chart.test.js`, `data.test.js`

**Interfaces — Produces:**
- `data.js`: `bestFor(pogoda, cell, hBySpecies: {key: h}, dayIdx) -> { species, score, wx: weatherFor(...) } | null`
- `map.js`: `fillColorExpression(pogoda, "all", dayIdx)` / `fillOpacityExpression` — `["max", e_1, …, e_6]` z wyrażeń gatunków (każde z własnym `weatherMatch`; brak pogody → −1); bez pogody → `max` z `h_*`
- `chart.js`: `chartDataBy(pogoda, scoreAt, todayIso)`, `trendBy(pogoda, scoreAt, dayIdx)` (`scoreAt(idx) -> number|null`); `chartData`/`trend` stają się wrapperami
- `ranking.js`: `topN(..., species = "all", ...)` — wynik wiersza = `bestFor`, grupa ma `species`

- [ ] **Step 1: Failing tests:** wyrażenie `all` zawiera `"max"` i `h_` każdego gatunku; bez pogody → `max` z `h_*`; `bestFor` pomija gatunki bez danych i zwraca `null` gdy żaden; ranking `all` zwraca `species` najlepszego; `chartDataBy`/`trendBy` z prostym `scoreAt` dają te same wyniki co dotychczasowe funkcje; stara fixture `pogoda_v1.json` + `all` → bez wyjątku.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Commit `feat(web): tryb Wszystkie gatunki (mapa, ranking, wykres)`.

---

### Task 4: UI — select, popup `all`, karta gatunku, „Jak to działa?”

**Files:** Modify `web/js/ui.js`, `web/js/popup.js`, `web/index.html`, `web/css/app.css`; Create `web/js/dialogs.js`; Test `web/tests/dialogs.test.js`

**Interfaces — Produces:** `dialogs.js`: `speciesCardModel(info, key) -> { title, latin, season, partners, preferred, adjacent, age, description, lookalikes, wiki, unreviewed } | null` (czyste), `renderSpeciesCard(model) -> HTMLElement`, `aboutForecastText(generatedAt) -> string` („Prognoza z: 3 paź, 05:00” lub „brak prognozy”); `RISK_COLORS = { niejadalny: "#fdd835", trujący: "#fb8c00", "śmiertelnie trujący": "#d32f2f" }`.

- [ ] **Step 1: Failing tests:** `speciesCardModel` z przykładowego `info` (teksty z Global Constraints: sezon, „od 30 lat”, disclaimer niezależny od modelu), `info null` → `null`; `aboutForecastText(null) === "brak prognozy"`.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** UI: `init()` najpierw `await loadSpecies()`, potem `parseHash`; select z „Wszystkie gatunki” na górze; ⓘ (`aria-label="Opis gatunku"`) otwiera kartę (`showModal`), przycisk „Zamknij”; `info null` → „Brak opisu gatunku”; popup `all` (lista gatunków z paskami, reszta dla najlepszego); „Jak to działa?” w stopce i w legendzie (`pointer-events` legendy włączone tylko dla linku); `<dialog>` przewijalny, max-height 85dvh; topbar 375 px bez zawijania.
- [ ] **Step 6:** Commit `feat(web): karta gatunku, Jak to działa, popup trybu Wszystkie gatunki`.

---

### Task 5: Weryfikacja end-to-end

- [ ] **Step 1:** Compose + Playwright: `s=all` koloruje mapę (różni się od samego borowika w miejscu, gdzie inny gatunek wygrywa — znajdź takie wydzielenie w Pythonie), ranking pokazuje gatunek, popup listę; karta gatunku dla każdego z 6 gatunków otwiera się i zamyka (przycisk, Esc), zawiera sobowtóry i disclaimer; „Jak to działa?” z datą prognozy; usunięty `gatunki.json` (tymczasowo) → mapa działa, karta „Brak opisu gatunku”; 375 px: topbar i dialogi (zrzuty); konsola bez błędów JS.
- [ ] **Step 2:** `down -v`, usuń override i przywróć pliki; pełne testy; poprawki jako `fix: …`.
