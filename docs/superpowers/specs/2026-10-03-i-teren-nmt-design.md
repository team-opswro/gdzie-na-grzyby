# I. Teren: wilgotność topograficzna (TWI) i ekspozycja z NMT — projekt

Data: 2026-10-03
Status: zaakceptowany (rozmowa 2026-10-03)
Zakres: nowy krok pipeline'u `pipeline.terrain` liczący dla każdego wydzielenia TWI, nachylenie i wystawę z Copernicus DEM GLO-30; dwa nowe statyczne czynniki siedliska w `h`.
Poza zakresem: dynamiczne powiązanie terenu z pogodą (zmieniłoby formułę klienta i format centroidów — decyzja z 2026-10-03), wysokość n.p.m. jako czynnik, NMT 1 m z GUGiK, nowe atrybuty w kafelkach.

## 1. Cel

Siatka pogodowa 0,1° (ok. 7–11 km) nie widzi mikroklimatu: obniżenia i stoki północne dłużej trzymają wilgoć, strome stoki południowe przesychają. Statyczny czynnik terenu przesuwa `h` w obrębie komórki pogodowej.

**Kryterium sukcesu:** `python -m pipeline.terrain` tworzy `pipeline/data/terrain.parquet` dla ≥ 99% wydzieleń z `stands.parquet`; raport `pipeline.validate` (spec H) pokazuje AUC siedliska nie gorsze niż przed zmianą dla każdego gatunku z wystarczającą liczbą obserwacji; czynnik, którego ablacja nie obniża AUC żadnego gatunku, zostaje ustawiony na neutralny przed wdrożeniem. `pipeline.build` bez `terrain.parquet` działa jak dziś.

## 2. Dane: Copernicus DEM GLO-30

- Publiczny bucket AWS (bez logowania): `https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM/Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM.tif`.
- Kafle 1° × 1° przecinające bbox `pipeline/data/obszar.geojson` (rząd 10–15 kafli, każdy ~25–40 MB). Kafel nieistniejący (404) → pominięty z ostrzeżeniem.
- Cache: `pipeline/data/raw/dem/` (już w `.gitignore`); ponowny przebieg nie pobiera, chyba że `--refresh`.
- Licencja: Copernicus DEM — wolne użycie z atrybucją; dopisujemy „Copernicus DEM GLO-30 © DLR e.V. 2010–2014 i © Airbus Defence and Space GmbH 2014–2018, dostarczone w ramach programu Copernicus” do atrybucji źródeł w `docs/data/api.md` i do listy „Źródła i licencje” w `web/index.html` (obok BDL).

## 3. Przetwarzanie (`pipeline/terrain.py`)

1. **Mozaika i rzutowanie:** `rasterio.merge` kafli → przycięcie do bbox obszaru + bufor 2 km (żeby spływ na brzegach nie był ucięty) → `rasterio.warp.reproject` do EPSG:2180, piksel 30 m, resampling bilinear. Raster pośredni w `pipeline/data/build/dem_2180.tif`.
2. **Hydrologia (`pysheds`):** wypełnienie zagłębień (`fill_pits`, `fill_depressions`), rozwiązanie płaskich obszarów (`resolve_flats`), kierunki spływu D8, akumulacja.
3. **Nachylenie i wystawa:** z gradientu (`numpy.gradient` na rastrze 2180) — nachylenie β w radianach, wystawa 0–360° (0 = N, zgodnie z ruchem wskazówek).
4. **TWI:** `ln(a / tan β)`, gdzie `a = (akumulacja + 1) × 30 m` (powierzchnia zlewni na jednostkę szerokości konturu), `tan β` ograniczone od dołu do `tan(0.1°)` (płaskie piksele nie dają ∞).
5. **Statystyki strefowe (`rasterstats.zonal_stats`, `all_touched=True`):** dla każdego wydzielenia z `stands.parquet` przerzutowanego do EPSG:2180: mediana TWI, średnie nachylenie (°), kołowa średnia wystawy (z `sin`/`cos` — dwa rastry, `atan2` średnich), udział pikseli; wydzielenie bez pikseli → wiersz pominięty.
6. **Klasy:**
   - `twi_class` ∈ {`DRY`, `MID`, `WET`}: tercyle mediany TWI po wszystkich wydzieleniach obszaru (progi zapisane w `terrain.parquet` jako metadane i w `build.json`, żeby były porównywalne między buildami);
   - `exposure` ∈ {`S_STEEP`, `OTHER`}: `S_STEEP`, gdy nachylenie > 10° i wystawa w [135°, 225°].
7. **Wynik:** `pipeline/data/terrain.parquet` (już objęty `pipeline/data/*.parquet` w `.gitignore`): `prefix`, `a_i_num`, `twi`, `slope`, `aspect`, `twi_class`, `exposure`.

Pamięć: raster obszaru 30 m to rząd 5·10⁷ pikseli float32 (~0,2 GB na warstwę, kilka warstw naraz); krok uruchamiany w kontenerze `grzyby-pipeline` jak `pipeline.build`. Gdy pamięć nie wystarcza — przetwarzanie po nadleśnictwach (obrys + bufor 2 km), progi tercyli liczone na końcu po całości; wybór wariantu w planie po pomiarze.

## 4. Model

### 4.1. Ingest i `Stand`

`load_stands` dołącza `terrain.parquet` po `(prefix, a_i_num)` (left join), jeśli plik istnieje; `Stand` dostaje pola `twi_class: str | None = None`, `exposure: str | None = None`. Klasy (nie wartości ciągłe) trafiają do klucza cache w `build_tiles`, więc liczba unikalnych kluczy rośnie co najwyżej 6×.

### 4.2. Czynniki

Dwa nowe czynniki w mechanizmie ze specu F (§4.1–4.2): tabele w `species.yaml`, wchodzą do iloczynu `mod` z dolnym ograniczeniem `MOD_FLOOR`, brak danych → 1.0, raportowane w `habitat_components`.

**`twi` — klasa TWI** (`factors_default.twi` pusta → 1.0). Nadpisania:
- `kozlarz`: `DRY` 0.85;
- `maslak`, `kurka`: `WET` 0.85.

**`exposure`** (`factors_default.exposure`): `S_STEEP` 0.85, `OTHER` 1.0 — dla wszystkich gatunków.

Wartości startowe stroi raport ze specu H.

### 4.3. Zależność od specu F

Spec I używa rejestru czynników, tabel `factors_default`/`factors` i `MOD_FLOOR` ze specu F. Jeśli I byłby wdrażany przed F, plan I zawiera minimalną wersję tego mechanizmu (tylko dla `twi` i `exposure`), którą F potem rozszerza.

## 5. Uruchamianie i kontener

```sh
podman run --rm -v $PWD:/w:z -w /w grzyby-pipeline python -m pipeline.terrain [--refresh]
```

Kolejność: `ingest` → `terrain` → `build`. `pipeline/requirements.txt` + obraz (`pipeline/Dockerfile`): `rasterio`, `pysheds`, `rasterstats` (wheels z GDAL dla linux/aarch64 i amd64 — weryfikacja w planie). `CLAUDE.md` i `docs/` — dopisanie kroku do listy poleceń pipeline'u.

## 6. Kontrakt danych

Bez zmian w plikach publikowanych poza: `build.json` dostaje progi tercyli TWI (`terrain: {"twi_terciles": [t1, t2], "dem": "GLO-30"}`) oraz atrybucję w `docs/data/api.md` (§2). Kafelki i centroidy bez zmian.

## 7. Testy

- `tests/test_terrain.py`:
  - syntetyczny DEM (rynna w kształcie V, 50 × 50 px): TWI na dnie doliny > TWI na grzbiecie; płaski raster nie daje `inf`/`nan`;
  - wystawa: płaszczyzna nachylona na południe → ~180°, na północ → ~0°; kołowa średnia dla 350° i 10° → ~0°;
  - klasy: tercyle na znanym rozkładzie; `S_STEEP` dla 15° i 180°, `OTHER` dla 5° i 180° oraz 15° i 0°;
  - statystyki strefowe na dwóch poligonach w EPSG:2180;
  - lista kafli GLO-30 dla bbox (nazwy URL), pominięcie 404 (mock `responses`).
- `tests/test_habitat.py`: czynniki `twi`/`exposure`, brak klasy → 1.0.
- `tests/test_ingest.py`: `load_stands` bez `terrain.parquet` → kolumny `None`; z plikiem → dołączone klasy.
