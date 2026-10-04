# Wrocław, Miękinia, Milicz i Twardogóra

Data kontroli: 2026-10-04. Wdrożenie: <https://grzyby.demo.opswro.com/>.

## Dane rzeczywiście dostępne w aplikacji

Sprawdzono konfigurację `/config.json`, manifest, nazwy nadleśnictw,
kafelki rankingu, prognozę i fragmenty archiwum PMTiles przez HTTP Range.
Konfiguracja używa `/dane/`; manifest wskazuje wersję `20261004-1408-12d72c4`.

Zbiór zawiera 72 nadleśnictwa, 335 689 wydzieleń, 278 282 punkty rankingu
oraz 665 komórek pogodowych. Obecne są Miękinia (`13-17`), Milicz (`13-18`),
Oborniki Śląskie (`13-19`), Oleśnica Śląska (`13-09`), Oława (`13-20`),
Żmigród (`13-31`) i Wołów (`13-06`). Twardogóra jest pokryta danymi
Oleśnicy Śląskiej i Milicza. Syców (`09-19`) nie występuje w tym zbiorze.

| Okolica | Punkty rankingu do 10 km od sprawdzonego środka | Wydzielenia w próbnym kafelku z=12 |
|---|---:|---:|
| Miękinia | 1544 | 427 |
| Milicz | 1901 | 556 |
| Twardogóra | 2061 | 302 |

Wszystkie wymienione punkty miały dodatni wynik dla co najmniej jednego gatunku
w dniu kontroli. Kafelki zawierają warstwy `lasy`, `parkingi` i `rezerwaty`.
Serwer poprawnie zwraca zakresy PMTiles jako `206 Partial Content`.
To potwierdza obecność danych; kontrola nie obejmowała wizualnego renderowania
w przeglądarce, ponieważ narzędzie obsługi przeglądarki było niedostępne.

## Zmiana widoku i wdrożenie

Domyślny widok znajduje się na Wrocławiu (`17.033, 51.11`, zoom 10).
Selektor **Okolica** otwiera również Miękinię, Oborniki Śląskie, Oleśnicę Śląską,
Oławę, Milicz, Twardogórę i Opole. Miękinia, Milicz i Twardogóra otwierają się
przy zoomie 12, aby łatwiej obejrzeć wydzielenia.

Wybór okolicy przenosi ranking do środka mapy, otwiera panel i wyłącza wcześniejszy
punkt GPS. Spóźniona odpowiedź geolokalizacji nie cofa tego wyboru. Ręczne przesunięcie
mapy ustawia selektor na „Bieżący widok mapy”. Linki do konkretnych miejsc zachowują
pierwszeństwo przed widokiem domyślnym; adres z `c=` pod Opolem nadal otworzy Opole.

Zmiany znajdują się w frontendzie. Należy wdrożyć nowy obraz `web`; istniejący zbiór
R2 wystarcza do pokazania sprawdzonych okolic. Moduły `js/areas.js`, `js/driving.js`
i `js/parkings.js` należą do powłoki PWA, której wersję pamięci podręcznej zwiększono do 3.

Przykładowe adresy, działające również z dotychczasowym frontendem:

- [Miękinia](https://grzyby.demo.opswro.com/#s=all&d=0&z=12&c=51.192,16.739)
- [Milicz](https://grzyby.demo.opswro.com/#s=all&d=0&z=12&c=51.527,17.271)
- [Twardogóra](https://grzyby.demo.opswro.com/#s=all&d=0&z=12&c=51.365,17.468)

## Limit 50 km samochodem

Nowe wejście bez parametrów wybiera tryb samochodowy i limit 50 km. Obliczenie
jest uruchamiane przyciskiem **Oblicz dojazd**. Początkowo start wyznacza środek
mapy lub GPS; potem pozostaje stały podczas oglądania miejsc. **Start z mapy**,
zmiana okolicy lub GPS pozwalają wybrać inny punkt wyjazdu. Link przechowuje
tryb jako `t=car` i przybliżony start jako `o=lat,lon`; wcześniejsze linki bez
tego parametru zachowują tryb w linii prostej.

`parkings.js` odczytuje punktową warstwę parkingów z istniejącego archiwum PMTiles
przy zoomie 11, z cache i limitem czasu pobierania. Dla punktu w lesie wybierane
są maksymalnie trzy najbliższe parkingi do 1,5 km w linii prostej. Ten dystans
nie jest długością trasy pieszej ani potwierdzeniem dostępności ścieżki.

`driving.js` pobiera macierz długości i czasów najszybszych tras samochodowych
z OSRM/FOSSGIS. Zapytania są kolejkowane z odstępem ponad sekundy i wykonywane
po kliknięciu przycisku; współrzędne startu i parkingów trafiają do tej usługi.
Trasy są filtrowane po niezaokrąglonej długości do 50 000 m. Brak trasy,
parking ponad 100 m od dopasowanej drogi i brak pobliskiego parkingu powodują
pominięcie miejsca. Awaria usługi pokazuje błąd; nie stosuje odległości w linii
prostej jako zamiennika. Czas nie uwzględnia korków.

Sprawdzanych jest do 200 najwyżej ocenionych oddziałów, od największego wyniku,
aż uda się znaleźć dziesięć propozycji. Jeśli limit kandydatów zostanie osiągnięty
z krótszą listą, aplikacja pokazuje informację o ograniczeniu. Link nawigacji
prowadzi do parkingu, a kliknięcie wiersza pokazuje punkt w lesie.

Próbne zapytanie do [OSRM/FOSSGIS](https://routing.openstreetmap.de/about.html)
z centrum Wrocławia zwróciło około 27 km do sprawdzonego parkingu pod Miękinią
i około 59 km do wybranych parkingów pod Miliczem i Twardogórą. To pojedyncze
trasy kontrolne, nie ocena odległości do wszystkich lasów w tych okolicach.

API BDL może uzupełniać brakujące nadleśnictwa, ale import nie zapewnia pełnych
opisów taksacyjnych i domieszek z paczek. Przed publikacją rozszerzonego zbioru
trzeba zachować dotychczasowe dane, przebudować siatkę i odświeżyć prognozę.
