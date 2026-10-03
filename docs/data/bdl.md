# Dane BDL (Bank Danych o Lasach) — rozpoznanie

Data rozpoznania: 2026-10-03. Status: dane dostepne, bramka ryzyka PRZECHODZI z zastrzezeniem (brak domieszek, patrz nizej).

## Skad i na jakich warunkach
- Portal: https://www.bdl.lasy.gov.pl/portal/ ; strona uslug: https://www.bdl.lasy.gov.pl/portal/uslugi-ogc
- **OGC API Features** (bez logowania, bez wniosku): https://ogcapi.bdl.lasy.gov.pl (kolekcje `nadlesnictwa`, `lesnictwa`, `rdlp`, `RDLP_<nazwa>_wydzielenia`). Zapytania CQL dzialaja (`filter=adr_for LIKE '02-40%'&filter-lang=cql-text`), stronicowanie `limit`<=1000 + `offset`, `f=json` (GeoJSON, EPSG:4326).
- WFS: https://wfs.bdl.lasy.gov.pl/geoserver/BDL/ows (te same warstwy). WMS drzewostanow: https://mapserver.bdl.lasy.gov.pl/arcgis/services/WMS_BDL_mapa_drzewostanow/MapServer/WMSServer
- Alternatywa: paczka SHP + opisy taksacyjne (tekst) per nadlesnictwo przez wniosek interaktywny https://www.bdl.lasy.gov.pl/portal/wniosek (wymaga akceptacji warunkow, link pobrania przychodzi e-mailem; nie uzyto). Opis taksacyjny w tej paczce moze zawierac gatunki domieszkowe — NIEZWERYFIKOWANE.
- **Licencja/warunki** (Regulamin https://www.bdl.lasy.gov.pl/portal/regulamin, pkt III i V): dostep powszechny i nieodplatny; ponowne wykorzystanie wg ustawy o dostepie do informacji publicznej; obowiazek podania zrodla, czasu wytworzenia/pozyskania informacji i udostepniania w pierwotnej formie; dane maja charakter pogladowy, bez odpowiedzialnosci za rzetelnosc. Uzycie hobbystyczne dozwolone. W aplikacji podac: "Zrodlo: Bank Danych o Lasach (BDL), PGL Lasy Panstwowe, stan 2026 (a_year=2026)".

## Struktura wydzielen (warstwa `RDLP_*_wydzielenia`)
Jeden rekord (MultiPolygon, EPSG:4326) = jedno wydzielenie; **atrybuty drzewostanu w tej samej warstwie, brak osobnej tabeli do zlaczenia**.

| kolumna | typ | znaczenie / przyklady |
|---|---|---|
| a_i_num | int | unikalny identyfikator wydzielenia (np. 240004275) |
| adr_for | str | adres lesny `RR-NN-L-OOO  -x  -pp`, np. `02-40-1-05-612   -c   -00` (RR=RDLP, NN=nadlesnictwo) |
| area_type | str | rodzaj powierzchni; `D-STAN` = drzewostan |
| species_cd | str | gatunek panujacy (kod) |
| spec_age | int | wiek gatunku panujacego (lata) |
| part_cd | str | udzial gatunku panujacego w skladzie w dziesiatych (`10` = czysty, `5`...) |
| site_type | str | typ siedliskowy lasu (kod) |
| stand_stru | str | struktura: `DRZEW`, `KO`, `KDO`, `2 PIĘT` |
| silvicult | str | `P-Z` (przebudowa/zagospodarowanie), `S`, `Z`, `N` |
| sub_area | float | powierzchnia ha |
| rotat_age, forest_fun, prot_categ, nazwa, a_year | | wiek rebnosci, funkcja (`GOSP`,`REZ`,`REZ CZ`; używana do oznaczania rezerwatów, razem z obrysami z GDOŚ), kategoria ochronnosci (`OCH USZK`,`OCH MIAST`,`OCH WOD`), nazwa pakietu, rok stanu (2026) |

### Przykladowe wartosci (nadl. Opole, 6687 wydzielen, pobrane do pipeline/data/raw/opole_wydzielenia.gpkg — nie commitowane)
- species_cd (D-STAN): SO 4758, DB 421, BRZ 331, OL 271, BK 48, MD 34, DB.S 15, GB 15, DB.C 15, LP 8, DB.B 5, OS 5, TP 5, JW 5, ŚW 5, JS 4, AK 3, DG 2, SO.C 1, OL.S 1, WZ 1. Kody z kropka = odmiany/podgatunki (DB.S szypulkowy, DB.B bezszypulkowy, DB.C czerwony) — do sprowadzenia do rdzenia przed mapowaniem.
- site_type: BMŚW 1561, BMW 1407, LMW 1284, BŚW 836, LMŚW 780, LW 148, OL 78, LŁ 40, LŚW 33, BMB 32, LMB 19, BW 17, BB 2 (+ puste dla nie-lasu).
- spec_age: 0..182, mediana 47 (0 dla nie-drzewostanow).
- part_cd: 10: 2040, 7: 830, 8: 726, 6: 719, 9: 591, 5: 556, 4: 337, 3: 139, 2: 15.
- Przyklad: `a_i_num=240026456, area_type=D-STAN, species_cd=SO, spec_age=57, site_type=BMW, part_cd=10, stand_stru=DRZEW, sub_area=2.17`.

## Klucz `id` = adres lesny (adr_for)
`fields.id` = `adr_for` (spec §5). Surowa wartosc ma wewnetrzne dopelnienie spacjami, np. `02-40-1-12-363   -i   -00` (Lodz: `06-01-2-13-201B  -b   -00`). **Regula normalizacji dla loadera: usunac wszystkie biale znaki** (`re.sub(r"\s+", "", v)`) -> `02-40-1-12-363-i-00`. Po normalizacji (i bez niej) `adr_for` jest unikalny w probce Opole (6687 rekordow, 0 duplikatow). Filtr CQL po nadlesnictwie dziala na surowej wartosci (`LIKE '02-40%'`; prefiks to poczatek bez spacji). `a_i_num` pozostaje alternatywnym kluczem numerycznym. Unikalnosc w calym woj. do potwierdzenia przy pelnym pobraniu (prefiks nadlesnictwa jest w adresie, wiec kolizje miedzy nadlesnictwami sa wykluczone).

## Domieszki
**Warstwa udostepniana przez OGC API/WFS nie zawiera gatunkow domieszkowych**: jest tylko gatunek panujacy (`species_cd`) z jego wiekiem i udzialem (`part_cd`; wartosc < 10 oznacza, ze reszta skladu to inne gatunki, ale nieznane). Brak duplikatow a_i_num/adr_for (1 rekord = 1 wydzielenie). Pelny sklad (z domieszkami) jest w opisie taksacyjnym paczki z wniosku interaktywnego — nie sprawdzono. Dla spec. v1 (gatunek panujacy + wiek + siedlisko) dane wystarczaja; `sp_admix: null`.

## Odroznianie nie-lasu
`area_type`: `D-STAN` (5952 w Opolu) = drzewostan; reszta to grunty nieleśne/niezalesione, m.in. `ZRĄB` 144 (zreb, brak gatunku), `L ENERG` 89 (linie energet.), `R` 69, `Ł` 58, `SUKCESJA` 56, `INNE WYL`, `DROGI I`, `BAGNO`, `PS`, `POL ŁOW`, `STAW R-R`, `URZ WOD`, itd. Dla nie-D-STAN `species_cd` jest null, `spec_age`=0, `stand_stru`/`part_cd` null. Filtr (w YAML: `values: ["D-STAN"]`, `require_not_null: [species_cd]`): `area_type == 'D-STAN'` i `species_cd` niepusty (jedyny wyjatek: `PLANT NAS` z gatunkiem — pomijamy). Uwaga: D-STAN obejmuje tez mlode uprawy (wiek 1-10) i `KO`/`KDO` (kultury) — decyzja o minimalnym wieku nalezy do modelu.

## Granice nadlesnictw i nadlesnictwa przecinajace woj. opolskie
Kolekcja `nadlesnictwa` (429 obiektow; pola `inspectorate_name`, `region_cd`, `inspectorate_cd`). Przeciecie z granica woj. (OSM relacja 224460), km2 w woj. / calosc: Prudnik 1806/1809, Namyslow 810/811, Tulowice 717/717, Kluczbork 698/698, Opole 695/695, Strzelce Opolskie 673/673, Brzeg 664/665, Proszkow 586/586, Rudy Raciborskie 495/1022, Olesno 459/471, Kup 406/406, Kedzierzyn 345/358, Turawa 302/302, Zawadzkie 245/286, Wielun 189/1462, Lubliniec 186/521, Rudziniec 104/582, Klobuk 14/862. Wszystkie oprocz Wielunia (RDLP Lodz, region 06) naleza do RDLP Katowice (region 02) — czyli **RDLP Wroclaw nie wnosi nic istotnego** (tylko slivery <1.1 km2: Syców, Henryków, Oława, Bardo Śląskie, Przedborów, Herby, Oleśnica Śląska). Obszar: lasy PGL LP; lasy prywatne/inne poza zakresem tej warstwy.

## Granica wojewodztwa
`pipeline/data/opolskie.geojson`: OSM relacja 224460 (Nominatim, polygon_geojson), uproszczona do 100 m w EPSG:2180, zapisana w EPSG:4326, ~28 kB, 9400.7 km2. Atrybucja: (c) wspolautorzy OpenStreetMap, ODbL.

## Ostrzezenia
- Dane BDL sa poglądowe (regulamin); wiek/gatunek ze stanu 2026.
- Pobranie calego woj.: ok. 18 nadlesnictw x ~5-8 tys. rekordow; stronicowac po 1000 z filtrem `adr_for LIKE 'RR-NN%'`. Pole `numberMatched` w odpowiedziach z filtrem bywa nierzetelne — stronicowac do pustej/niepelnej strony.

## Mapowanie nadlesnictw (bdl_fields.yaml `districts`)
Kazdy wpis: `name` (jak `inspectorate_name`), `prefix` (`region_cd-inspectorate_cd`, kody z kolekcji `nadlesnictwa`), `layer`. 17 nadlesnictw w RDLP Katowice (region 02), Wieluń 06-20 w `RDLP_Lodz_wydzielenia`, Henryków 13-02 i Oława 13-20 w `RDLP_Wroclaw_wydzielenia` (`whole: true`).

## Nadleśnictwa spoza województwa, włączone w całości (RDLP Wrocław)
Henryków (`13-02`) i Oława (`13-20`), dolnośląskie przy Grodkowie, warstwa `RDLP_Wroclaw_wydzielenia`; w `bdl_fields.yaml` oznaczone `whole: true`. Format `adr_for` jak w innych RDLP (np. `13-02-1-03-63    -b   -00`), filtr `LIKE '13-02%'` działa. Dane pobrane w całości (Henryków 2663, Oława 4662 wydzieleń D-STAN), bez przycinania do granicy woj.
Obrys z kolekcji `nadlesnictwa` (`region_cd='13' AND inspectorate_cd IN ('02','20')`) jest łączony z `opolskie.geojson` krokiem `python -m pipeline.area` do `pipeline/data/obszar.geojson` (EPSG:4326, uproszczony do 100 m w EPSG:2180); build kafelków przycina do tego pliku. Nowe kody siedlisk: `BMWYZ` (1 wydz.) dodany jako odpowiednik `BMW`; `OLJWYZ` (18) nie ma odpowiednika na listach gatunków (jak `OLJ`, `OL`, `LL`) i dostaje współczynnik "inne siedlisko".
