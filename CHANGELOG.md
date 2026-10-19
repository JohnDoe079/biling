# CHANGELOG — Biling Toolkit
Format wersji: RRRR-MM-DD GG:MM (data godzina:minuty)

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
