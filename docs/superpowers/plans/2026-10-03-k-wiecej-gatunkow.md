# K. Więcej gatunków i tryb grupy — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 18 gatunków w 5 grupach (+ kurka), zestawy siedlisk w `species.yaml`, grupy w `gatunki.json` i tryb grupy w aplikacji (mapa, popup, ranking), bez zerowych `h_*` w kafelkach.

**Architecture:** `forecast/species.py` rozwija `@zestawy` i czyta `group`; `pipeline/species_info.py` dokłada `group`/`groups` do `gatunki.json`; `build_tiles` pomija zerowe `h_*`. W `web/` wybór (gatunek / `g-<grupa>` / `all`) jest rozwiązywany do listy kluczy, a dotychczasowy tryb „all” staje się trybem wielogatunkowym na dowolnej liście.

**Tech Stack:** Python 3, PyYAML, pytest; plain ES modules + `node --test`.

**Spec:** `docs/superpowers/specs/2026-10-03-k-wiecej-gatunkow-design.md`

**Zależność:** nadpisania czynników dla nowych gatunków (spec §2.2, ostatni akapit) wchodzą tylko jeśli plan F jest już wykonany — wtedy w Task 1; inaczej plan F dopisuje je w swoim Task 4.

## Global Constraints

- Komentarze, komunikaty, teksty UI, commity po polsku (`feat(pipeline): …`, `feat(web): …`, `feat(gatunki): …`).
- Parametry 12 nowych gatunków **dokładnie** wg tabeli spec §2.2; zestawy siedlisk dokładnie wg spec §2.3; kolejność w `species.yaml`: obecne 6 w obecnej kolejności, potem nowe w kolejności tabeli.
- `rydz`: nazwa „Rydz mleczaj”, `partners: [SO]`, klucz bez zmian.
- Grupy i ich teksty dokładnie wg spec §3; `kurka` bez grupy.
- Hash grupy: `s=g-<grupa>`; prefiks `GROUP_PREFIX = "g-"`.
- `<select>`: „Wszystkie gatunki”, potem `optgroup` na grupę (pierwsza opcja = tekst `all` grupy, wartość `g-<grupa>`), na końcu `optgroup` „Inne”.
- Treści: `content/gatunki.yaml` — sobowtóry obowiązkowe wg spec §2.4 (nazwy, łacina, ryzyko dosłownie); nowe kody drzew `OS` osika, `TP` topola, `GB` grab, `MD` modrzew; `reviewed: false` bez zmian.
- `h_<gatunek> = 0` pomijany w GeoJSONSeq; klient traktuje brak jako 0.
- Testy: `.venv/bin/pytest -q`, `node --test web/tests/*.test.js`.

## Review Focus

1. **Stary link `#s=kozlarz` / `#s=all` / `#s=rydz`** — otwiera ten sam wybór co przed planem (rydz teraz = rydz mleczaj). Test w Task 4.
2. **Brak `gatunki.json` (timeout)** — awaryjna lista 18 gatunków bez grup; `#s=g-kozlarze` → domyślny gatunek, bez wyjątku. Test w Task 4.
3. **Wydzielenie bez żadnego `h_*` w kafelku** (wszystkie zera) — popup w trybie grupy pokazuje paski z wartością 0/„–”, mapa „słabo/brak”, bez `NaN`. Test w Task 5.
4. **Gatunek w `index.species` centroidów, którego nie ma w `gatunki.json`** (stary build + nowy klient lub odwrotnie) — ranking pomija nieznane kolumny, nie przesuwa indeksów. Test w Task 5.
5. **Popup w trybie grupy, gdy żaden gatunek grupy nie ma pogody w komórce** — „Brak danych pogodowych…”, paski po samym `h`. Test w Task 5.

---

### Task 1: Zestawy siedlisk, grupy i nowe gatunki w `species.yaml`

**Files:**
- Modify: `forecast/species.py`, `species.yaml`
- Test: `tests/test_species.py`, `tests/test_habitat.py`

**Interfaces:**
- Produces:
  - `load_species` czyta `habitat_sets` z korzenia YAML; `_expand(items: list[str], sets: dict) -> frozenset[str]` — element `@nazwa` → kody zestawu, inne bez zmian; nieznany zestaw → `ValueError`; po rozwinięciu `habitat_adjacent -= habitat_preferred`.
  - `Species.group: str | None = None` (z pola YAML `group`).
  - `species.yaml`: `habitat_sets`, `group` przy gatunkach grup, zmiana `rydz`, 12 nowych gatunków.

- [ ] **Step 1: Testy**

```python
def test_habitat_set_expansion(tmp_path):         # preferred: ["@bory_ubogie", "LSW"] -> {"BS","BSW","BGSW","LSW"}
def test_unknown_set_raises(tmp_path):
def test_code_in_both_lists_stays_preferred(tmp_path):
def test_repo_has_18_species_in_order():          # list(S)[:6] == ["borowik","podgrzybek","kurka","kozlarz","maslak","rydz"]; len(S) == 18
def test_groups_assigned():                       # S["kozlarz_czerwony"].group == "kozlarze"; S["kurka"].group is None; S["rydz"].group == "rydze"
def test_rydz_only_pine():                        # S["rydz"].partners == {"SO"}; S["rydz_swierkowy"].partners == {"SW"}
# test_habitat.py:
def test_aspen_on_lmsw_good_for_red_bolete():     # Stand("OS", (), 40, "LMSW") -> habitat_score(kozlarz_czerwony) >= 0.9; Stand("SO", (), 40, "BSW") -> 0
def test_larch_only_for_larch_bolete():           # Stand("MD", (), 30, "LMSW") -> maslak_zolty > 0; Stand("SO", (), 30, "LMSW") -> maslak_zolty == 0
def test_spruce_rydz_vs_pine_rydz():              # Stand("SW", (), 30, "BMSW") -> rydz_swierkowy > 0, rydz == 0
def test_existing_species_scores_unchanged():     # dla kilku Stand: borowik/podgrzybek/kurka/kozlarz/maslak — wartości sprzed planu (zapisz je w teście przed zmianą yaml)
```

- [ ] **Step 2: Uruchom** `.venv/bin/pytest tests/test_species.py tests/test_habitat.py -q` — FAIL.
- [ ] **Step 3: Implementacja** wg Interfaces i tabeli spec §2.2 (przy wykonanym planie F — także nadpisania czynników z §2.2).
- [ ] **Step 4: Uruchom** `.venv/bin/pytest -q` — PASS (poza `test_species_info.py`, który wymaga treści z Task 2 — jeśli failuje z „brak treści gatunku”, to oczekiwane; Task 2 to naprawia). Ruling w ledgerze, jeśli tak się stanie.
- [ ] **Step 5: Commit** `feat(gatunki): 12 nowych gatunków, zestawy siedlisk i grupy`

---

### Task 2: Treści i `gatunki.json`

**Files:**
- Modify: `content/gatunki.yaml`, `pipeline/species_info.py`
- Test: `tests/test_species_info.py`

**Interfaces:**
- Consumes: `species.yaml` z Task 1 (surowy YAML — `build_info(species_yaml, content)` rozwija `@zestawy` przez wspólną funkcję `_expand` z `forecast/species.py`).
- Produces:
  - `content/gatunki.yaml`: `codes.trees` + `OS`, `TP`, `GB`, `MD`; sekcja `groups` (spec §3); 12 wpisów `species.<klucz>` z `latin`, `wiki`, `description` (2–4 zdania), `lookalikes` wg spec §2.4; `rydz` — opis zaktualizowany do rydza mleczaja (sosna), sobowtóry bez zmian.
  - `build_info` → każdy gatunek z polem `group` (klucz lub `None`); korzeń z `groups: [{"key", "name", "all", "species": [...]}]` w kolejności pierwszego wystąpienia; grupa bez tekstów lub teksty bez grupy → `ValueError`.

- [ ] **Step 1: Testy**

```python
def test_groups_in_info():               # info["groups"][0]["key"] == "borowiki"; kozlarze.species == ["kozlarz", "kozlarz_czerwony", ...]
def test_species_have_group_field():     # kurka -> None, maslak_zolty -> "maslaki"
def test_missing_group_texts_raises():   # usunięcie groups.rydze z content -> ValueError
def test_new_tree_codes_translated():    # maslak_zolty.partners == ["modrzew"]; kozlarz_czerwony.partners == ["osika", "topola"]
def test_habitat_sets_expanded_in_info():  # borowik_sosnowy.habitats_preferred zawiera "bór suchy"
def test_required_lookalikes_present():  # rydz_swierkowy: nazwy {"Mleczaj wełnianka", "Mleczaj omszony"}, oba "trujący"; borowik_sosnowy zawiera "Borowik szatański"
```

- [ ] **Step 2: Uruchom** `.venv/bin/pytest tests/test_species_info.py -q` — FAIL.
- [ ] **Step 3: Implementacja**; opisy pisać rzeczowo (kapelusz, hymenofor, trzon, miąższ i przebarwienie, siedlisko/partner), bez porad kulinarnych poza jadalnością; przebudować `web/data/gatunki.json` nie trzeba (generowany przez build).
- [ ] **Step 4: Uruchom** `.venv/bin/pytest -q` — PASS; `.venv/bin/python -m pipeline.species_info --help` lub pełne wywołanie do katalogu tymczasowego — bez błędu.
- [ ] **Step 5: Commit** `feat(gatunki): opisy i sobowtóry nowych gatunków, grupy w gatunki.json`

---

### Task 3: Bez zerowych `h_*` w kafelkach

**Files:**
- Modify: `pipeline/build_tiles.py` (`write_geojsonseq`), `docs/data/api.md`
- Test: `tests/test_build_tiles.py`, `web/tests/map.test.js`, `web/tests/popup.test.js`

**Interfaces:**
- Produces: GeoJSONSeq bez kluczy `h_<k>` o wartości 0; `api.md`: „brak atrybutu `h_<gatunek>` = 0”. Klient: każde miejsce odczytu `h_*` w `web/js/` (`map.js` `hExpr`, `popup.js` `speciesBars`/`renderPopup`, `ui.js`) daje 0 dla braku — potwierdzone testami (bez zmian kodu, jeśli już tak jest; jeśli nie — poprawka).

- [ ] **Step 1: Testy**

```python
def test_geojsonseq_omits_zero_h(tmp_path):    # wydzielenie z h_borowik 0, h_kurka 55 -> props bez "h_borowik", z "h_kurka": 55
```
```js
test("hExpr: brak atrybutu = 0", ...)         // fillColorExpression ewaluowana (istniejący helper testów) na props bez h_* -> klasa "brak"
test("popup: brak h_* = 0", ...)              // renderPopup z props bez h_borowik -> „Siedlisko 0%”
```

- [ ] **Step 2: Uruchom** — Python FAIL; JS zgodnie z obecnym zachowaniem (jeśli PASS od razu — to potwierdzenie istniejącego zachowania, zapisać w ledgerze jako wynik weryfikacji, nie jako test RED).
- [ ] **Step 3: Implementacja**.
- [ ] **Step 4: Uruchom** `.venv/bin/pytest -q && node --test web/tests/*.test.js` — PASS.
- [ ] **Step 5: Commit** `perf(pipeline): pomijanie zerowych ocen siedliska w kafelkach`

---

### Task 4: Wybór gatunku/grupy w aplikacji

**Files:**
- Modify: `web/js/data.js`, `web/js/hash.js`, `web/js/ui.js`
- Test: `web/tests/data.test.js`, `web/tests/hash.test.js`, `web/tests/ui`-owe testy w istniejącym pliku najbliższym tematu (np. `web/tests/dialogs.test.js` nie — nowy `web/tests/select.test.js`)

**Interfaces:**
- Produces (w `web/js/data.js`):
  - `SPECIES` — awaryjna lista 18 gatunków (klucz, nazwa) w kolejności `species.yaml`.
  - `GROUP_PREFIX = "g-"`.
  - `groupsOf(info) -> Array<{key, name, all, species: string[]}>` — `info?.groups ?? []`.
  - `selectionKeys(sel: string, speciesList, groups) -> string[]` — `ALL` → wszystkie klucze; `g-x` → `species` grupy `x` (przecięte z `speciesList`); klucz gatunku → `[klucz]`; nieznane → `[]`.
  - `isMulti(sel) -> boolean` — `sel === ALL || sel.startsWith(GROUP_PREFIX)`.
  - `selectionValues(speciesList, groups) -> string[]` — wszystkie dozwolone wartości (`ALL`, `g-*`, klucze) dla `parseHash`.
  - `buildSpeciesOptions(selectEl, speciesList, groups)` — w `web/js/ui.js` lub nowym `web/js/select.js` (czysta funkcja na elemencie DOM, testowalna z `dom-stub.js`): struktura z Global Constraints.
- `ui.js`: `syncInfoBtn` używa `isMulti`; `parseHash(location.hash, selectionValues(...))`.

- [ ] **Step 1: Testy**

```js
test("selectionKeys: grupa, all, gatunek, nieznane", ...)
test("parseHash akceptuje g-kozlarze i stare klucze", ...)    // "#s=g-kozlarze" -> species "g-kozlarze"; "#s=kozlarz" -> "kozlarz"; "#s=g-xyz" -> domyślny
test("buildSpeciesOptions: optgroup na grupę + Inne", ...)   // pierwsza opcja "all"; optgroup "Koźlarze (kozaki)" zaczyna się od "Wszystkie koźlarze" (g-kozlarze); ostatni optgroup "Inne" z kurką
test("bez gatunki.json: 18 gatunków, brak grup, g-kozlarze -> domyślny", ...)
```

- [ ] **Step 2: Uruchom** `node --test web/tests/data.test.js web/tests/hash.test.js web/tests/select.test.js` — FAIL.
- [ ] **Step 3: Implementacja** wg Interfaces; `dom-stub.js` rozszerzyć o `optgroup`, jeśli brakuje.
- [ ] **Step 4: Uruchom** `node --test web/tests/*.test.js` — PASS.
- [ ] **Step 5: Commit** `feat(web): wybór grupy gatunków i lista z podziałem na grupy`

---

### Task 5: Tryb wielogatunkowy na liście kluczy (mapa, popup, ranking)

**Files:**
- Modify: `web/js/map.js`, `web/js/popup.js`, `web/js/ranking.js`, `web/js/ui.js`
- Test: `web/tests/map.test.js`, `web/tests/popup.test.js`, `web/tests/ranking.test.js`

**Interfaces:**
- Consumes: `selectionKeys`, `isMulti` (Task 4).
- Produces:
  - `fillColorExpression(pogoda, keys: string[], dayIdx)`, `fillOpacityExpression(pogoda, keys, dayIdx)` — `keys.length === 1` → wyrażenie jednogatunkowe jak dziś; więcej → `max` po `keys` (dotychczasowe `allExpression` sparametryzowane listą; stała `ALL_KEYS` usunięta). `addForestLayers`/`setView` przyjmują `keys` zamiast `species`.
  - `renderPopup(props, ctx)` — `ctx.keys: string[]` zamiast porównania z `ALL`; tryb wielogatunkowy gdy `keys.length > 1`: `hAll` i paski tylko dla `keys`, nagłówek z najlepszym gatunkiem.
  - `topN(centroids, pogoda, keys: string[], dayIdx, origin, radiusKm, n)` — kolumny wybierane po `centroids.species.indexOf(k)` dla `k ∈ keys` (nieznane pominięte); jedna kolumna → tryb jednogatunkowy; wiele → `bestFor` po `keys`; grupa w wyniku ma `species` (najlepszy) w trybie wielu.
  - `ui.js`: jedno miejsce `const keys = () => selectionKeys(state.species, speciesList, groups)` używane przez mapę, popup, ranking i trend (`state.species === ALL` zastąpione `keys().length > 1`).

- [ ] **Step 1: Testy**

```js
test("fillColorExpression dla grupy = max po jej gatunkach", ...)   // ewaluacja na props: h_kozlarz 80, h_kozlarz_czerwony 20, pogoda w=1 -> klasa wg 80
test("fillColorExpression dla jednego klucza jak dawniej", ...)     // porównanie z wynikiem sprzed zmiany (snapshot JSON wyrażenia)
test("popup grupy: paski tylko gatunków grupy", ...)               // keys = 5 koźlarzy -> 5 elementów li.ps-*
test("popup grupy bez pogody", ...)                                // -> „Brak danych pogodowych…”, paski po h
test("popup: wydzielenie bez h_*", ...)                            // keys grupy, props bez h -> paski „–”/0, bez NaN
test("topN grupy: najlepszy gatunek z grupy", ...)
test("topN pomija klucze spoza centroids.species", ...)            // keys z nieznanym kluczem -> ranking z pozostałych, indeksy kolumn poprawne
```

- [ ] **Step 2: Uruchom** `node --test web/tests/map.test.js web/tests/popup.test.js web/tests/ranking.test.js` — FAIL.
- [ ] **Step 3: Implementacja** wg Interfaces; istniejące testy trybu `all` przepisać na `keys` (zachowując asercje).
- [ ] **Step 4: Uruchom** `node --test web/tests/*.test.js` — PASS.
- [ ] **Step 5: Commit** `feat(web): tryb grupy na mapie, w popupie i w rankingu`

---

### Task 6: Pomiary rozmiaru

Wykonywany po pełnym buildzie (koordynator, po planach F/K/I/J) — kroki tu, żeby wynik trafił do historii.

- [ ] **Step 1:** Rozmiary przed: z `pipeline/data/out/` sprzed buildu (`lasy.pmtiles` 112 MB, `centroidy/` 19 MB — stan 2026-10-03) i `web/data/live/pogoda.json` 0,6 MB.
- [ ] **Step 2:** Po buildzie w kontenerze (`podman run … python -m pipeline.build`) i lokalnym przebiegu prognozy (`docker compose -f docker-compose.local.yml --profile forecast run --rm forecast`): zmierzyć te same pliki i czas buildu.
- [ ] **Step 3:** Jeśli `lasy.pmtiles` urósł > 40% — ruling: dodatkowa redukcja (np. `hl_*` tylko przy `h ≥ 40`, zaokrąglenie `h` do 5) i ponowny pomiar. Jeśli `pogoda.json` > 2 MB przed gzip — pomijanie tablic składowych równych w całości 0 (spec §5) z testem w `tests/test_run.py`, aktualizacją schematu i `api.md`.
- [ ] **Step 4: Commit** (jeśli były zmiany) z tabelą rozmiarów w opisie.
