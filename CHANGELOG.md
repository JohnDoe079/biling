# CHANGELOG — Biling Toolkit
Format wersji: RRRR-MM-DD GG:MM (data godzina:minuty)

## 2026-10-14 21:09
### Dodane
- Generowanie raportow DOCX obok CSV (nowy modul raporty_docx.py, wymaga
  python-docx): raport per numer, raport urzadzenia (IMEI), raport zbiorczy
  krzyzowy. Uklad A4 PORTRET, tabele na 100% szerokosci strony, naglowki
  tabel powtarzane na kazdej stronie. Brak python-docx = komunikat,
  CSV/TXT generuja sie normalnie.

## 2026-10-14 21:02
### Zmienione
- Raport krzyzowy osobocentryczny: sekcja A grupuje analizowanych po kluczu
  wtornym (PESEL osoby / NIP-KRS firmy) — nazwa, identyfikator, wszystkie
  numery, operatorzy, urzadzenia (IMEI), liczba zdarzen. Sekcja A2 = dawna
  sekcja A (wykaz numerow). Sekcja B agreguje komunikacje do par osob
  (X kontaktowal sie N razy z Y). Sekcje C i D bez zmian.

## 2026-10-14 20:36
### Zmienione
- common.format_numer(): 9 cyfr = numer polski (komorkowy lub stacjonarny)
  -> doklejamy 48; wyjatki bez zmian: wiodace 0 oraz numer zaczynajacy sie
  od 48 (kod kierunkowy Radomia w formacie krajowym). Ujednolicenie form
  (48x / 0048x / x) jako ten sam klucz dzialalo juz wczesniej (klucz_numer).

## 2026-10-14 19:28
### Dodane
- Wzbogacenie danymi abonenckimi kontaktow bedacych analizowanymi numerami
  z INNYCH zrodel/sieci: operator podaje dane abonentow tylko ze swojej
  sieci, wiec raporty per numer korzystaja z globalnej mapy danych
  abonenckich ze wszystkich folderow (wlasciwe dane wygrywaja).
- Sekcja B raportu krzyzowego: kolumny "Dane abonenta (od)/(do)".

## 2026-10-14 19:22
### Zmienione
- Raporty trafiaja do podfolderu <outdir>/RRRR-MM-DD_GGMM (data i godzina
  uruchomienia skryptu).

## 2026-10-14 18:56
### Zmienione
- Wymaszkowano wszystkie dane przykladowe (numery telefonow) w kodzie,
  komentarzach, README i CHANGELOG — zasada: NIGDZIE w projekcie
  dane wrazliwe, wyłacznie maskowane placeholdery (np. 48XXXXXXXXX).

## 2026-10-14 18:51
### Dodane
- Preambula OGLĘDZIN DANYCH TELEKOMUNIKACYJNYCH na wstepie kazdego raportu
  (per numer i per urzadzenie, TXT i CSV): formulka "Oględzinom poddano
  dane telekomunikacyjne dostarczone przez operatora X dla numeru/urzadzenia Y
  za okres od ... do ...", folder abonenta, listing plikow zrodlowych
  z sumami kontrolnymi SHA-256 (common.sha256_pliku).
- Sekcja 5 (urzadzenia): kolumna IMSI obok IMEI — najczestsza karta SIM
  uzywana z danym urzadzeniem.

## 2026-10-14 16:42
### Zmienione
- common.format_numer(): prefiks 48 TYLKO dla numerow polskich. 9-cyfrowy
  numer dostaje 48 wylacznie gdy zaczyna sie od 2-8 (polskie NSN nigdy nie
  zaczynaja sie od 0, 1, 9); 9 cyfr od 0/1/9 (np. zagraniczny numer
  w formacie krajowym) zostaje bez zmian.

## 2026-10-14 16:34
### Dodane
- common.format_numer(): prezentacja numerow Z prefiksem krajowym (48XXXXXXXXX).
  9 cyfr bez prefiksu = zakladamy numer polski (komorkowy lub stacjonarny)
  i doklejamy 48; 0048xxx -> 48xxx; numery zagraniczne bez zmian.
  Wszystkie raporty (per numer, urzadzenia, krzyzowy) i konsola pokazuja
  numery z prefiksem; wewnetrzne klucze porownan pozostaja kanoniczne.

## 2026-10-14 16:20
### Dodane
- analizaBilling.py jako ORCHESTRATOR: zero pytan interaktywnych; operator z nazwy
  folderu, pliki autowykrywane przez modul operators/<op>.py
- Tryb URZADZENIA (IMEI): autodetekcja zestawow kluczowanych po IMEI (parametry
  zadania / identyfikator strony A / nazwa folderu); raport urzadzenia pokazuje
  jakie MSISDN byly uzywane w telefonie (IMSI, okres, kontakty, BTS)
- Raport ZAWSZE per numer — rowniez dla pustych danych i braku parsera operatora
- Zestaw z SAMYMI danymi abonenckimi (zapytanie po karcie SIM): numer brany
  z wierszy danych; w raporcie SIM, forma (pre-paid/NPLAN), status, okres
- operators/plus.py: pola SIM, Typ MSISDN, Status w parserze danych abonenckich;
  datasets() nie pomija zestawu z samym plikiem dane_abonenckie
- Flagi CLI: --dane, --outdir, --numer, --bez-krzyzowej, --txt
- Konsola: podsumowanie wykrytych zestawow + lista numerow MSISDN i urzadzen IMEI
- analizaKrzyzowa: rekordy tryb="imei" pomijane w sekcjach B/C, ich IMEI
  w sekcji D (wspolne urzadzenia)

### Zmienione
- Raporty per numer/urzadzenie domyslnie tylko CSV; TXT generuje flaga --txt
- Porownania numerow kanonikalizowane (48xxx -> xxx) we wszystkich funkcjach
  analizy — naprawia puste sekcje dla bilingow Plus z prefiksem 48
- Przetestowane na realnych plikach QR (wykaz pusty + dane abonenckie z karta SIM)

### Poprawione
- FutureWarning (fillna/downcasting) w kontakty_zdarzenia/kontakty_sms
- argparse: --bez-krzyzowej -> args.bez_krzyzowej

## 2026-10-14 14:55
### Dodane
- Klucze identyfikacyjne: MSISDN (podstawowy) + PESEL/NIP-KRS (wtorny); imie/nazwa wylacznie do wyswietlania
- Scalanie zrodel o tym samym MSISDN w jeden rekord (rozne zapytania/pliki = ta sama osoba)
- Sekcje raportu zbiorczego z identyfikatorem PESEL/NIP-KRS i flaga "ta sama osoba/firma"
- operators/plus.py: parser w pelni przetestowany na realnych plikach systemu QR
  (naglowek dynamiczny, numer z "Parametrow zadania", mapa typow, dane abonenckie z NIP-em,
  transmisja danych, obsluga plikow pustych i samych-transmisji)
- numer zagraniczny (np. XXXXXXXXXXX) przechodzi bez zmian; polski z 48/0048 jest normalizowany

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
