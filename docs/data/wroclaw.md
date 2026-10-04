# Wrocław: analiza pokrycia i dojazd do 50 km

Data: 2026-10-04. Dokument opisuje rozpoznanie i proponowany zakres rozszerzenia;
nie potwierdza dostępności lasów w żadnym działającym wdrożeniu.

## Jak działa projekt

- `pipeline.ingest` wczytuje paczki BDL z `Nadlesnictwa/` do DuckDB i GeoParquet.
  Obsługuje również dane OGC API wskazane w `pipeline/bdl_fields.yaml`.
  Paczka ma pierwszeństwo przed API dla tego samego nadleśnictwa.
- `pipeline.build` oblicza oceny siedliska dla 18 gatunków, oznacza rezerwaty,
  buduje PMTiles, kafelki punktów rankingu oraz siatkę pogodową.
- `forecast` pobiera pogodę Open-Meteo i oblicza prognozę: impuls deszczu,
  bilans wody podłoża, temperaturę, przymrozki i sezon gatunku.
- `web/` to statyczna aplikacja MapLibre. Wynik 0–100 łączy ocenę siedliska
  z pogodą; nie jest skalibrowanym prawdopodobieństwem znalezienia grzybów.
- Dane produkcyjne są publikowane na R2; lokalnie nginx może serwować
  `pipeline/data/out/`. Frontend nie wymaga procesu kompilacji JavaScript.

## Co wiadomo o okolicach Wrocławia

README deklaruje 72 nadleśnictwa RDLP Katowice i Wrocław. `docs/data/bdl.md`
wymienia wcześniejsze dodanie nadleśnictw poniżej, a także Henrykowa, Żmigrodu
i Milicza. To opis historycznego zbioru, nie sprawdzenie aktualnych plików.

| Nadleśnictwo | Kod BDL | Kierunek poszukiwań |
|---|---|---|
| Miękinia | `13-17` | zachód i południowy zachód |
| Oborniki Śląskie | `13-19` | północ i północny zachód |
| Oleśnica Śląska | `13-09` | północny wschód |
| Oława | `13-20` | wschód i południowy wschód |

W tej kopii nie ma `Nadlesnictwa/`, `pipeline/data/`, środowiska `.venv`
ani adresu wdrożenia. `api_districts` jest puste. Sam kod nie wystarczy do
wyświetlenia ocen lasów. Nadleśnictwa nie są równoznaczne z konkretnymi
miejscówkami dostępnymi w 50 km jazdy.

Sprawdzono publiczne API BDL: zwraca obrysy nadleśnictw wokół Wrocławia
oraz wydzielenia Miękini, np. `13-17-1-01-190-j-00`, sosna, 63 lata,
`LMŚW`, stan 2026. API pozwala uruchomić mapę bez paczek, lecz import
nie zapewnia pełnych opisów taksacyjnych i domieszek dostępnych w paczkach.

## Dlaczego obecny ranking nie spełnia limitu samochodowego

`web/js/ranking.js` mierzy odległość wzorem haversine, od środka mapy lub GPS.
Do wyboru jest 5, 10, 20 i 40 km. Mapa domyślnie startuje pod Opolem.
Linki nawigacyjne otwierają zewnętrzne mapy; długość dojazdu nie filtruje rankingu.

Punkty rankingu leżą wewnątrz wydzieleń. Ranking grupuje je po oddziale,
pomija rezerwaty oraz korzysta tylko z wydzieleń z oceną siedliska co najmniej
40 dla któregoś gatunku. Parkingi OSM są osobną warstwą, bez powiązania z rankingiem.

## Zakres realizacji

1. **Zbiór Wrocław:** skonfigurować pobieranie wymienionych nadleśnictw przez API
   lub dostarczyć paczki. Sprawdzić brakujące lasy na obrzeżach, np. Wołów.
   Import API musi działać również bez katalogu paczek. Po imporcie zbudować
   nazwy, rezerwaty, parkingi, kafelki i prognozę dla nowej siatki.
2. **Punkt startu:** udostępnić Wrocław jako wybór okolicy oraz możliwość
   wskazania rzeczywistego miejsca wyjazdu. Kilometry liczyć w jedną stronę.
3. **Dojazd:** połączyć miejsca z parkingami lub sprawdzonymi punktami dostępu.
   Wyznaczać trasy samochodowe do tych punktów, filtrować po niezaokrąglonej
   długości do 50 000 m, dopiero potem wybierać top 10. Pokazywać kilometry,
   orientacyjny czas i odległość punktu dostępu od lasu. Brak trasy oznaczać
   jako brak danych o dojeździe.
4. **Weryfikacja:** sprawdzić pokrycie mapy, świeżość pogody, dojazdy i obsługę
   błędów routingu. Dodać przypadek miejsca bliskiego w linii prostej,
   lecz oddalonego o ponad 50 km drogą. Aktualne zakazy wstępu sprawdzać w BDL.

## Źródła i sprawdzenia

- [BDL OGC API](https://ogcapi.bdl.lasy.gov.pl/): kolekcje `nadlesnictwa`
  i `RDLP_Wroclaw_wydzielenia` sprawdzone podczas analizy.
- [RDLP Wrocław: nadleśnictwa okalające miasto](https://www.wroclaw.lasy.gov.pl/aktualnosci/-/asset_publisher/BIu9rkka92Nd/content/sesja-rady-miejskiej-wroclawia-z-udzialem-nadlesniczy-1).
- [OSRM API](https://project-osrm.org/docs/v5.22.0/api/): trasy oraz macierze
  odległości samochodowych; próbne zapytanie do FOSSGIS zwróciło odległości drogowe.
- [Zasady FOSSGIS](https://routing.openstreetmap.de/about.html): publiczny serwer
  wymaga atrybucji i ogranicza ruch do jednego żądania na sekundę;
  dobór usługi należy uwzględnić przy implementacji.
- `node --test web/tests/*.test.js`: 185 testów, wszystkie przeszły.
  Testów Python nie uruchamiano: brak środowiska projektu.
