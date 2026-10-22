# CHANGELOG — Biling Toolkit
Format wersji: RRRR-MM-DD GG:MM (czas polski)

## 2026-10-21 22:05
### Zmienione (DOCX)
- Sekcja 1: Numer wyrównany do LEWEJ (wykluczony z centrowania);
  SMS i Polaczenia (W/P/PR) cap 5 — jednakowa szerokosc, 3 znaki;
  Razem podloga 6 znakow (naglowek sie nie zawija)
- Sekcja 3: Kod BTS cap 13, Wychodzace/Przychodzace cap 11 (mniejsze)

## 2026-10-21 22:00
### Zmienione (DOCX)
- Szerokosci: algorytm STALA/FLEX — kolumny waskie (cap<=15, min 5 znakow)
  maja stala szerokosc we wszystkich tabelach (Lp ~1.1 cm w kazdej
  sekcji, identycznie); kolumny elastyczne (tekst) dziela pozostala
  przestrzen; gdy brak elastycznych — przeskalowanie do 100% strony
- Jawne wyrównanie do lewej dla kolumn tekstowych (Abonent nie jest
  juz centrowany); centrowane liczby/daty naglowki i dane
- Sekcja 3 (DOCX i XLSX): kolumny Lp/Kod BTS/Adres/Wychodzace/
  Przychodzace (jednolite w obu formatach)

## 2026-10-21 21:45
### Zmienione (DOCX)
- Lp wszedzie szerokosc cap 4 znaki (waskie, jak w sekcji 3)
- Sekcja 2 INTERNET: dodana kolumna Lp (Lp/Adres IP/Liczba sesji/Od/Do);
  naprawione statystyki (sesje, czas — wczesniej zera)
- Sekcja 3 BTS: dodane kolumny Inicjujace/Odbierajace (jednolicie z XLSX)
- Numer cap 15 (koniec zawijania cyfr), W/P/PR cap 6 (3 znaki sie mieszcza)
- Centrowanie danych i naglowkow w kolumnach liczbowych/datowych (cap<=15);
  tekst (Numer/Abonent/Adres) bez zmian — do lewej
- Wykrywanie naglowkow dwupoziomowych po tresci ("Lp" w wierszu 2),
  nie po indeksie tabeli (dzialalo zle przy pustej sekcji 1)
### Uwaga
- XLSX: szerokosci bez zmian (jak ustalono — za duzo scalan w plaskim arkuszu);
  funkcjonalnosc identyczna w obu formatach

## 2026-10-21 21:25
### Dodane
- Inteligentne szerokosci kolumn (DOCX i XLSX): pomiar zawartosci
  z capami per kategoria (common.CAPY_KOLUMN) — Lp/liczniki waskie
  (~1 cm), daty 11, numery 13, nazwy/adresy 35-40 z zawijaniem,
  SHA-256 66, IP 42; normalizacja do 100% szerokosci
- DOCX: layout FIXED + nadpisany tblGrid (Word respektuje szerokosci,
  koniec recznych korekt)

## 2026-10-21 21:10
### Naprawione
- Nazwy kontaktow: "Nie znaleziono"/"nieznaleziono" -> "brak danych"
  (filtr rozszerzony o slowo "znaleziono"; regula generyczna)

## 2026-10-21 21:05
### Naprawione
- Etykiety abonentow: w galezi "same dane abonenckie" brakowalo podstawienia
  numeru — po zmianie obie etykiety z numerem w nawiasie, bez "#1"

## 2026-10-21 20:55
### Zmienione
- Krzyzowy: WYCOFANY TXT — zbiorczy = DOCX + XLSX (jednolicie z per numer);
  generuj_raport_zbiorczy przepisany na czysty XLSX (bez L/CSV);
  oględziny jednokrotnie z rozmiarem w obu formatach
### Naprawione
- DOCX zbiorczy: tabela oględzin 4 kolumny z naglowkiem + styl tabel

## 2026-10-21 20:45
### Naprawione
- Zbiorczy: usuniete duplikaty sekcji oględzin (3x -> 1x); folder analizowany
  raz, nie per numer
### Dodane
- Oględziny: kolumna Rozmiar (KB/MB/GB + bajty) przy kazdym pliku

## 2026-10-21 20:35
### Naprawione
- Zbiorczy krzyzowy XLSX: usuniety duplikat _wb.save (plik byl zepsuty);
  pelny test pipeline przechodzi, xlsx otwiera sie poprawnie

## 2026-10-21 20:20
### Zmienione
- Naglowki tabel DOCX: wypelnienie D9D9D9 (ciemniejsze niz wiersze F2F2F2)
- Sekcja BTS DOCX: jednolite z XLSX (adres w kolumnie Adres, kod -> (brak kodu))
- Pogrubienie TYLKO naglowkow (parametr n_naglowkow; pierwszy wynik normalny)

## 2026-10-21 19:50
### Zmienione
- Tabele DOCX: Table Grid (siatka, bez niebieskiego), pogrubione naglowki
  (Lp i grupowe), szare pasy co drugi wiersz danych od wiersza 2
  (wywolanie helpera na koncu — po zbudowaniu wszystkich tabel);
  XLSX: szare pasy co drugi wiersz

## 2026-10-21 19:40
### Zmienione
- Sekcja 1: Lp jako pierwsza kolumna (Numer, Abonent za Lp)
- Kosmetyka naglowka DOCX: tytul 16pt; "Operator: <nazwa operatora>";
  kazdy wiersz danych osobno; zmniejszone odstepy (2pt po akapicie)

## 2026-10-21 19:30
### Zmienione
- Sekcja 1: brak nazwy = "brak danych" (bez "nieustalony", ujednolicone);
  naglowki kolumn: "Numer" (pelny numer kontaktu) i "Abonent" (nazwa/dane);
  bez kolumny Lp w wierszu danych

## 2026-10-21 19:20
### Naprawione
- Sekcja 1: pelny_numer nie zwraca juz pustego stringa dla nietekstowych
  identyfikatorow (ING, krotkie numery); polacz_kontakty przywraca scalanie
  nazw z mapy (suffix _s obslugiwany); klucz mapy szukany po klucz_numer
  i pelnym numerze

## 2026-10-21 19:15
### Naprawione
- Sekcja 1: kolumna Nazwa nie znika przy laczeniu SMS z glosowymi
  (selektywny merge); wywolania polacz_kontakty z poprawnym parametrem

## 2026-10-21 19:00
### Dodane
- Zbiorczy krzyzowy DOCX: sekcje A-D jako tabele (Calibri 10) + oględziny
  z SHA-256; krzyzowy folder = TXT + DOCX + XLSX
### Naprawione
- Zbiorczy XLSX: usuniety duplikat naglowka oględzin
### Zmienione
- Diagnostyka: traceback przy bledach raportow + "[!!] Folder bez rekordu"

## 2026-10-21 18:55
### Dodane
- Diagnostyka brakujacych raportow per numer: pelny traceback przy bledzie +
  podsumowanie "[!] Pominięto N raportow" + komunikaty "[!!] Folder bez rekordu"
  przy wczytywaniu (latwo zobaczyc co odpada i dlaczego)
### Naprawione
- Zbiorczy krzyzowy: sciezka wyjscia .xlsx (byla .csv w komunikacie)

## 2026-10-21 18:45
### Zmienione
- Formatowanie: Calibri 10 w DOCX (Normal + Headings/Titile bold) i XLSX
  (wszystkie komorki; bold naglowkow sekcji zachowany)

## 2026-10-21 18:00
### Zmienione
- Oględziny z SHA-256 przeniesione z raportow per numer do raportu ZBIORCZEGO
  (listing wszystkich folderow abonentow, numeracja ciagla plikow)
- Sekcja 1: naprawione puste pole Abonent (klucz numeru rzutowany na tekst
  przed outer-joinem SMS z glosowymi)
- Nazwy kontaktow: komunikaty operatora ("numer nie obslugiwany przez...",
  "obsługiwany przez - Orange...") skracane do "brak danych"; pusta nazwa =
  "nieustalony" (regula generyczna na slowie "obslugiwany")

## 2026-10-21 17:45
### Zmienione
- Preambula oględzin w DOCX: naglowek + opis + TABELA plikow z SHA-256
  (spójna z formatem dokumentu, byle luźne akapity)
- Sekcja 1: dwupoziomowy naglowek ze scaleniem komórek (DOCX i XLSX):
  SMS (W|P), Polaczenia (W|P|PR), Razem; "nieustalony" zamiast "brak danych"

## 2026-10-21 17:25
### Dodane
- Preambula oględzin z SHA-256 na poczatku kazdego raportu per numer (DOCX i XLSX):
  listing wszystkich plikow zrodlowych folderu abonenta (*.xls/xlsx/pdf/csv/txt/docx)
  z sumami kontrolnymi; DOCX: akapity + page break, XLSX: pierwsze wiersze arkusza.
  Oględzinom poddaje sie cala przesylke — kazdy raport wymienia wszystkie pliki.

## 2026-10-20 15:40
### Zmienione
- Numery: normalizacja polskich — 48 odcinane TYLKO gdy wynik to 9 cyfr;
  zagraniczne (z kierunkowym operatora) i krotkie (SMS specjalne, 4-6 cyfr)
  bez zmian; w raportach wyswietlane pelne numery z prefixem 48
  (komorkowe i stacjonarne), zagraniczne i krotkie w oryginale

## 2026-10-20 15:15
### Zmienione
- TXT wycofany: raport per numer = DOCX + XLSX; zbiorczy krzyzowy = TXT + XLSX
- IMEI: kolumna "Abonent" zamiast "Uwagi" — imie/nazwa abonenta analizowanego
  albo numer + nazwa kontrahenta (do 3 numerow na urzadzenie)
- Adresy IP: kolumny Od/Do (zakres od pierwszego do ostatniego odnotowania)
  w DOCX i XLSX

## 2026-10-20 15:20
### Dodane
- Adresy IP: kolumny Od/Do (zakres od pierwszego do ostatniego odnotowania,
  przerwy mozliwe) w TXT/XLSX/DOCX

## 2026-10-20 15:10
### Zmienione
- UWAGA o "roznych urzadzeniach" w sekcji IMEI: tylko gdy >1 urzadzenie GLOWNE
  (urzadzenie analizowanego numeru). IMEI kontrahentow (innych osob) nie
  wyzwalaja uwagi.

## 2026-10-20 15:00
### Zmienione
- Raport zbiorczy krzyzowy: XLSX zamiast CSV (jednolicie dla wszystkich operatorow)
- IMEI kontrahenta: w Uwagach numer telefonu, ktory uzywal urzadzenia (+ nazwa jesli znana),
  do 3 numerow; format "kontrahent: 502572908 JAN KOWALSKI; 509192705"

## 2026-10-20 14:40
### Dodane
- IMEI: normalizacja do 14 cyfr bazowych (TAC+SNR; cyfra 15=check, 16=SVN —
  to samo urzadzenie liczone razem; struktura wg en.wikipedia.org/wiki/IMEI)
- IMEI: adnotacja czyjego urzadzenia — "glowne" (strona analizowanego numeru) vs
  "kontrahent" (IMEI drugiej strony polaczenia, przekazywane przez siec);
  objasnienie w sekcji 4 (TXT/XLSX/DOCX)
- analiza krzyzowa: sekcja D (IMEI wspolne dla wielu numerow) tez po kluczu 14-cyfrowym
### Zmienione
- Historie (abonent i kontakty): usunieta kolumna "Dane" (pelne/niepelne —
  redundantna; decyzja o pelnosci widoczna po zawartosci wiersza)

## 2026-10-20 14:30
### Zmienione
- Raport per numer: zamiast CSV generowany XLSX (openpyxl) — ta sama zawartosc,
  pogrubione naglowki sekcji, auto-szerokosc kolumn; wyjscie: <numer>_RAPORT_KONCOWY.xlsx
### Naprawione
- XLSX: wciecia w generatorze (cialo funkcji zostalo w definicji _w — pusty arkusz)

## 2026-10-20 14:15
### Naprawione
- CSV: domyslny blok raportu nie zawieral imsi/ip (podmiana trafila tylko w TXT) —
  sekcje IMSI i ADRESY IP brakowaly w CSV; wszystkie 3 formaty karmione
  tym samym blokiem danych (jedno zrodlo prawdy)

## 2026-10-20 14:05
### Naprawione
- Tryb reczny (--folder / wybor z listy): ip_dla_numeru wymagal kolumn a_key/b_key
  (istnieja tylko po analizie krzyzowej) — KeyError; teraz liczy klucze z stron,
  gdy kolumn brakuje. Tabela IP dziala w obu trybach.

## 2026-10-20 11:05
### Naprawione
- Sekcja IP: pelne adresy IPv6 w TXT (kolumna poszerzona do 42 znakow)

## 2026-10-20 10:55
### Dodane
- Sekcja INTERNET: tabela ADRESY IP (od najczesciej przyznawanych) w TXT/CSV/DOCX;
  parser Plus transmisji wyciaga kolumne IP
- Sekcja BTS: Plus nie podaje kodu BTS — adres stacji trafia do kolumny "Adres stacji",
  w "Kod BTS" wpis "(brak kodu)"

## 2026-10-20 10:45
### Naprawione
- Sekcje B i C raportu krzyzowego: brakujace kolumny FWD (przekierowania) —
  "Razem" liczyl FWD, a rozbicie nie pokazywalo (2 = 1 voice + 1 FWD; 133 vs 99)
### Dodane
- Kolumny "FWD przych"/"FWD wych" w sekcjach B i C (TXT+CSV); suma Razem =
  voice + proby + SMS + FWD + DATA (zweryfikowane: 0 niezgodnych wierszy)

## 2026-10-20 09:50
### Zmienione
- Kolejnosc raportu per numer: DANE ABONENTA (+historia) -> SEKCJA 1 POLACZENIA
  (kontakty) -> DANE OSOBOWE KONTAKTOW -> internet/BTS/IMEI/IMSI (TXT+CSV)
- Liczby zdarzen calkowite w CSV (nie 487.0 — fillna(0).astype(int) w polacz_kontakty)
- Kontakt bez danych = "brak danych" (bez nawiasow) w tabeli polaczen
### Naprawione
- Tytuly sekcji 1 ujednolicone w TXT/CSV/DOCX

## 2026-10-20 09:15
### Zmienione
- _polacz_nazwy(): kolejnosc rozniacych sie slow KANONICZNA (alfabetyczna) —
  zawsze jedna forma "nie obslugiwany przez Netia i Polkomtel",
  niezaleznie od kolejnosci wierszy w plikach operatora

## 2026-10-20 09:10
### Zmienione
- Sekcja "HISTORIA ZMIAN ABONENTOW KONTAKTOW" przemianowana na
  "DANE OSOBOWE KONTAKTOW (numery, z ktorymi kontaktowal sie analizowany)"
  (to dane kontaktow, nie historia zmian)
- Sortowanie numerow w tej sekcji NUMERYCZNE rosnaco (nie leksykograficzne)

## 2026-10-20 09:00
### Naprawione
- "blad raportu: float object has no attribute strip" — kontakt wystepujacy
  tylko w SMS mial NaN w zakresie czasu (polacz_kontakty); NaN czyszczone
- KeyError nazwa_kontaktu gdy SMS bez danych osobowych kontaktu — kolumna
  domyslnie pusta

## 2026-10-20 08:45
### Zmienione
- dedup_historia(): Plus odpowiada z DWOCH BAZ (Polkomtel + Netia) — wpisy
  bez twardych identyfikatorow o tym samym okresie scalane w jeden, teksty
  rozniace sie ostatnim slowem laczone naturalnie:
  "nie obslugiwany przez Polkomtel i Netia" (regula generyczna, bez nazw na sztywno)

## 2026-10-20 08:30
### Zmienione
- Sekcje 1+2 raportu per numer SCALONE w jedna tabele kontaktow (TXT+CSV+DOCX):
  kolumny SMS (wych/przych) NA POCZATKU, potem voice przych/wych, proby, Razem
  (suma wszystkich typow), czasy polaczen i zakres; kontakty tylko-SMS widoczne;
  dalsze sekcje przenumerowane (internet=2, BTS=3, IMEI=4, IMSI=5)

## 2026-10-20 08:20
### Dodane
- Historia abonenta/kontaktow: kolumny "Dane" (pelne/niepelne — twarde
  identyfikatory) i "Zrodlo" (plik, z ktorego wpis pochodzi; identyczne wpisy
  z roznych plikow scalane, zrodla laczone " | ")
- Sekcja historii abonenta widoczna takze przy pojedynczym wpisie

## 2026-10-19 22:45
### Dodane
- dedup_historia(): wpis pusty (bez twardego identyfikatora: PESEL/NIP/adres/SIM)
  znika, gdy jego okres pokrywa wpis z danymi; niepokryte luki zostaja
- Tokeny z SAMYMI dane_abonenckie nie sa pomijane — scalaja sie po MSISDN
  z tokenem wykazu (operator dzieli jeden numer na wiele zapytan)
- Mapa nazw: wpis z twardszymi identyfikatorami wygrywa — komunikat
  w polu nazwy nie nadpisuje wpisu z PESEL (dane z pliku 1QR z wieloma numerami)
### Zmienione
- datasets() Plus: grupy z samym dane_abonenckie przechodza dalej

## 2026-10-19 22:15
### Zmienione
- Wycofany sztywny filtr nazw abonentow (typu "nie obslugiwany") — dane przechodza
  jak w pliku zrodlowym; obsluga takich przypadkow do uzgodnienia pozniej

## 2026-10-19 22:10
### Zmienione
- Normalizacja stron przy PARSOWANIU (Plus i Orange): 48123456789 -> 123456789,
  wiec kontakt zapisany z prefixem 48 nie jest liczony jako osobny numer
- Filtr nazw abonentow rozszerzony: kazdy "nie obslugiwany" (Polkomtel, Netia, inne)
  znika z pola nazwy zamiast wyswietlac komunikat sieci

## 2026-10-19 22:00
### Zmienione
- KLUCZOWE: usuniety "swap" kolumn A/B w parserze Plusa — kolumny opisuja strony
  ZGODNIE Z POZYCJA (A = inicjujacy, B = odbierajacy). Poprzednio abonentowi
  przypisywano IMEI/IMSI kontrahentow z sieci Plus (wynikalo to fikcyjne
  "kilka urzadzen" zamiast 1)

## 2026-10-19 21:25
### Zmienione
- SEKCJA B (komunikacja bezposrednia): format zgodny z sekcja C —
  bloki par numerow z wierszami per abonent: numer, drugi numer, okres,
  razem, voice przych/wych, proby, SMS, DATA; flaga "ta sama osoba/firma" w naglowku pary

## 2026-10-19 21:20
### Zmienione
- SEKCJA A raportu krzyzowego: zamiast sumy wszystkich zdarzen telefonu
  liczniki zdarzen KRZYZOWYCH: "Z innymi" (sekcja B) i "Z kontakt." (sekcja C)

## 2026-10-19 21:10
### Zmienione
- SEKCJA C: kolumna abonenta = TYLKO numer telefonu; naglowek "Zdarzen z kontaktem"
  (jasne rozroznienie od "Liczba zdarzen" z sekcji A = wszystkie zdarzenia billingu)

## 2026-10-19 20:55
### Dodane
- SEKCJA C krzyzowa rozbita per abonent: okres kontaktow, przych/wych dla voice,
  prob, SMS/MMS oraz liczba transmisji DATA; nazwa kontaktu jesli znana z danych
### Zmienione
- Filtr smieci w polach BTS (Plus i Orange): komunikaty typu "przypisany do sieci",
  "nie byl w sieci Netia", "nieobslugiwany" sa czyszczone (nie pojawiaja sie w raportach BTS)

## 2026-10-19 20:45
### Zmienione
- Struktura wynikow poprawiona: output/<data_GGMM>/<numery>/ z normalnymi bilingami
  OBOK output/<data_GGMM>/krzyzowy/ zawierajacego WYŁACZNIE raporty krzyzowe
  (wczesniej per-numer ladowaly sie do srodka krzyzowy/)

## 2026-10-19 20:35
### Dodane
- RAPORT DOCX per numer (sekcje 1-6, tabele, historia abonenta; wymaga python-docx)
- Struktura wynikow: output/<RRRR-MM-DD_GGMM>/<numery>/ oraz output/<...>/krzyzowy/
  (raporty per numer + zbiorczy) przy analizie krzyzowej
### Zmienione
- Enter przy pytaniu o analize = analiza WSZYSTKICH folderow (domyslnie badamy wszystko)
- Przywrocony DOCX usuniety wczesniej przez blad; domyslny outdir to output/<data_GGMM>

## 2026-10-19 20:25
### Naprawione
- Przywrocony blok if __name__ == "__main__" w analizaBilling.py
  (skrypt konczyl sie bez wyjscia po usunieciu starego trybu recznego)

## 2026-10-19 20:15
### Usuniete
- Stary tryb reczny (wybor operatora 1-4, wpisywanie sciezek, zapytaj_o_plik) —
  zostala WYŁACZNIE autodetekcja: ./input (krzyzowa lub wybor folderu z listy)
  oraz --folder <sciezka> (operator zgadywany po plikach)

## 2026-10-19 15:10
### Zmienione
- Po odpowiedzi "n" w auto-skanie: lista wykrytych folderow do wyboru numerem
  (zamiast wpisywania sciezek); "r" = stary tryb reczny
- Pusty Enter przy sciezce = zakonczenie programu (bez traceback)

## 2026-10-19 14:05
### Zmienione
- TRYB RECZNY (analizaBilling.py): folder operatora obslugiwany przez modul tego operatora
  (pliki_z_folderu) — koniec sztywnego wzorca *_wykaz.pdf; dziala dla Orange (PDF) i Plus (XLS)
- Wiele zestawow w folderze recznym scala sie w jeden raport; numer brany z zestawu z danymi
- --folder bez --operator: operator zgadywany po rozszerzeniach plikow

## 2026-10-19 13:45
### Zmienione
- Usunieto FutureWarning przy scalaniu / budowaniu globalnej tabeli (puste ramki pomijane)

## 2026-10-19 13:24
### Dodane
- SEKCJA 6: KARTY SIM (IMSI) w raportach TXT+CSV (imsi_dla_numeru), z ostrzezeniem o wymianie SIM
- Parser Plus: typy UCA i PBXO, obsluga FORW z abonentem w kolumnie C (poczta 601222222)
- Czyszczenie cudzyslowow i komunikatow "Numer B przypisany do sieci: Plus" z BTS
### Zmienione
- KLUCZOWE: w exportach Plusa kolumny "A IMEI/A IMSI/A BTS ADDRESS" zawieraja ZAWSZE dane
  strony analizowanej — parser przenosi je na wlasciwa strone A/B
- raport per numer dla Plusa pokazuje: kontakty z kierunkami, BTS, IMEI (urzadzenia), IMSI (SIM)

## 2026-10-14 14:55
### Dodane
- Klucze identyfikacyjne: MSISDN (podstawowy) + PESEL/NIP-KRS (wtorny); imie/nazwa wylacznie do wyswietlania
- Scalanie zrodel o tym samym MSISDN w jeden rekord (rozne zapytania/pliki = ta sama osoba)
- Sekcje raportu zbiorczego z identyfikatorem PESEL/NIP-KRS i flaga "ta sama osoba/firma"
- operators/plus.py: parser w pelni przetestowany na realnych plikach systemu QR
  (naglowek dynamiczny, numer z "Parametrow zadania", mapa typow, dane abonenckie z NIP-em,
  transmisja danych, obsluga plikow pustych i samych-transmisji)
- numer zagraniczny (np. 79774264845) przechodzi bez zmian; polski z 48/0048 jest normalizowany

### Zmienione
- analizaKrzyzowa: zestawy z samym internetem nie sa pomijane; numer z zerem zdarzen jest wykazywany
- etykieta abonenta przy wielu zestawach w folderze: "<folder> (<numer>)"

## 2026-10-12 12:05
### Dodane
- Auto-skan ./input w analizaBilling.py i analizaKrzyzowa.py
- Autodetekcja realnych nazw plikow Plusa (grupowanie po ID zapytania), interfejs datasets()
### Zmienione
- usunieto folder przykladowy z input/ (zgodnie z uwaga: czyste input/)

## 2026-10-12 12:00
- Wersjonowanie paczek: biling_toolkit_RRRR-MM-DD_GGMM.zip
- README + VERSION.txt; puste foldery operatorow z README.txt w input/

## 2026-10-12 11:55
- Poprawka: plus.parse -> plus.parse_plus w analizaBilling.py

## 2026-10-12 11:45
- Szkielet v2: struktura input/, parser Plus (Excel), analiza krzyzowa (sekcje A-D)

## wczesniej — v1
- Tylko Orange, tryb pojedynczego numeru, raport TXT+CSV
