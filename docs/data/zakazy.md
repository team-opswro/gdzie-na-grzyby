# Okresowe zakazy wstępu do lasu (BDL) — rozpoznanie

Data rozpoznania: 2026-10-03. Wynik: **pozytywny z zastrzeżeniami** (patrz „Werdykt").

## Gdzie to naprawdę jest
- Strona `https://www.bdl.lasy.gov.pl/portal/zakazy-wstepu` („Zakazy wstępu (moduł user)") to tylko strona opisowa z linkiem do instrukcji PDF (v1.5). **Nie jest aplikacją JS z API.**
- Właściwa aplikacja: **https://zakazywstepu.bdl.lasy.gov.pl/zakazy/** (ASP.NET + ArcGIS JS 3.46; kod: `/zakazy/js/site.js`). Na stronie głównej: „obszary leśne na terenie 26 z 429 nadleśnictw. Stan na: 03.10.2026".
- Żądania aplikacji (z `site.js` i stopki strony):

| URL (względem `/zakazy/`) | metoda | odpowiedź |
|---|---|---|
| `Home/GetProhibitionsRSS` | GET | RSS 2.0 (`application/rss+xml`, kodowanie **windows-1250**), ~60 pozycji |
| `Home/GetProhibitionsForForestRangesAndCompartments` | GET | JSON `{"data":[{"forestRangeAddress":"01-02-2-04-216A"},...]}` |
| `Home/GetProhibitionsPDF` | GET | PDF „Lista zakazów" |
| `Home/GetInspectorates` | GET | JSON (bez logowania pusta lista `[]`) |
| `Home/GetForestRanges`, `Home/GetCompartments`, `Add/Cancel/ChangeEndDate` | | moduł zarządzania, wymaga logowania — nie używane |
| `https://mapserver.bdl.lasy.gov.pl/arcgis/rest/services/Mapa_zakazow_wstepu_do_lasu/MapServer` (warstwy 0–7) | GET | ArcGIS REST, geometria + atrybuty (`kod_nadl`, `nazwa_nadl`, `lesnictwo`, `adr_lesny`, `kod_oddzialu`, `data`, `data_koncowa`, `kod`) |

## (a) Czy działa bez sesji/ciasteczek
- RSS i JSON z `Home/*`: **tak** — `curl` bez ciasteczek i nagłówków, HTTP 200.
- ArcGIS MapServer: `curl` bez nagłówków dostaje **403 (nginx)**, tak samo jak `.../arcgis/services` (z briefu). Wygląda na bramkę po nagłówku `Referer` (jedno zapytanie z `Referer` aplikacji zwróciło 200 z opisem usługi). **Nie traktujemy tego jako źródła**: to obejście ograniczenia, nie publiczny kontrakt; dalszych zapytań tą drogą nie robiono.

## (b) Geometria / klucz
- RSS i JSON **nie mają geometrii**. Mają klucze:
  - JSON: adres leśny na poziomie leśnictwa (`RR-NN-L-LL`, np. `02-22-1-08`) albo oddziału (`RR-NN-L-LL-NNNx`, np. `01-02-2-04-216A`).
  - RSS: tekst „Zakaz wstępu w oddziałach 216A, ... leśnictwie X (nadleśnictwo Y) z przyczyny ..." + tytuł = leśnictwo.
- Klucze są zgodne z prefiksem `adr_for` z OGC API (`RR-NN-L-LL-NNN-x-pp`, patrz bdl.md): po usunięciu białych znaków, `RR-NN-L-LL` = leśnictwo (pasuje do prefiksu), a oddział `NNNx` = `NNN` + podział `x` (wielkość liter do ujednolicenia). Geometrię zakazu dałoby się więc złożyć z wydzieleń (`RDLP_*_wydzielenia`) lub kolekcji `lesnictwa` — bez dotykania MapServera.
- Kody zakazów w RSS: przyczyna „zagrożenie pożarowe" / „zabiegi ochronne" / „inne przyczyny" (legenda: czerwony / fioletowy / żółty).

## (c) Daty obowiązywania
- **RSS**: tak — „obowiązuje od 2025-03-12 07:56:44 do 2026-12-31 r." oraz `pubDate`. Zakazy bywają długie (do końca roku) lub bez daty końca (MapServer: `data_koncowa` może być null).
- **JSON `Home/*`**: tylko adresy, bez dat.
- Zakaz może być odwołany lub zmieniony w ciągu dnia (instrukcja: odwołanie, zmiana daty, automatyczne odwołanie po dacie końcowej) — dane trzeba odświeżać często, a w aplikacji pokazywać „stan na".

## (d) Regulamin BDL (`/portal/regulamin`)
- Pkt III: dostęp powszechny i nieodpłatny, dane wg ustawy o udostępnianiu informacji o środowisku; obowiązek podania źródła i czasu pobrania; dane poglądowe. Pkt VI: zabronione kody/skrypty „przerywające, niszczące lub ograniczające działanie BDL". **Brak wprost zakazu ani zgody na automatyczne pobieranie.** Małe, rzadkie zapytania (RSS raz na kilkanaście minut–godzinę) mieszczą się w duchu regulaminu; RSS jest zresztą udostępniany jako kanał do automatycznego odbioru. Regulamin serwisu `zakazywstepu.*` osobno nie znaleziono (stopka „© DGLP", odsyła do polityki ciasteczek BDL).

## Stan obecny dla obszaru projektu (2026-10-03)
Zakazy dotyczą 26 nadleśnictw (m.in. Białowieża, Nidzica, Konin, Olkusz, Jawor, Szklarska Poręba, Przedbórz). **Żadne nadleśnictwo z obszaru (RDLP Katowice woj. opolskie, Wieluń, Henryków, Oława) nie ma dziś zakazu.** Zakazy pożarowe pojawiają się sezonowo (lato, susza), więc warstwa byłaby zwykle pusta.

## (e) Werdykt: **pozytywny z zastrzeżeniami**
Kontrakt danych dla ewentualnego planu „7b":
1. Źródło: `GET https://zakazywstepu.bdl.lasy.gov.pl/zakazy/Home/GetProhibitionsRSS` (bez autoryzacji), dekodować jako windows-1250; z pozycji wyciągnąć: nadleśnictwo (nawias), leśnictwo (tytuł), listę oddziałów (regex po „w oddziałach ... ,"), przyczynę, daty od/do.
2. Opcjonalnie JSON `GetProhibitionsForForestRangesAndCompartments` jako czysta lista kluczy.
3. Geometria: składać z `lesnictwa` / wydzieleń OGC API po prefiksie adresu leśnego (filtr `LIKE 'RR-NN-L-LL%'`).
4. Filtr do obszaru: prefiksy nadleśnictw z `bdl_fields.yaml`.
5. Odświeżanie: po stronie klienta/CI, nie częściej niż co ~30–60 min; pokazywać „stan na" i link do `zakazywstepu.bdl.lasy.gov.pl`; atrybucja BDL/Lasy Państwowe.

Zastrzeżenia / co zostaje: (i) format RSS to nieudokumentowany tekst — parsowanie kruche, wymaga testów na pozycjach z leśnictwem bez oddziałów oraz bez daty końca (w próbce nie zaobserwowano pozycji dla obszaru); (ii) brak pozycji z naszego obszaru, więc nie sprawdzono rzeczywistego wyglądu zakazu dla opolskiego; (iii) nie ma oficjalnej zgody na automatyczne pobieranie (regulamin milczy); (iv) CORS niezbadany — odczyt z przeglądarki użytkownika może nie działać, wtedy potrzebny krok CI/cron. **Wersja minimalna (zawsze dostępna): sam link „Sprawdź aktualne zakazy wstępu" do `https://zakazywstepu.bdl.lasy.gov.pl/zakazy/`.** Implementacja warstwy to osobny plan po akceptacji użytkownika.
