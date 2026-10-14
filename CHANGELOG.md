# CHANGELOG — Biling Toolkit
Format wersji: RRRR-MM-DD GG:MM (data godzina:minuty)

## 2026-10-14 22:34
### Dodane
- common.format_numer(): prezentacja numerow Z prefiksem krajowym (48123456789).
  9 cyfr bez prefiksu = zakladamy numer polski (komorkowy lub stacjonarny)
  i doklejamy 48; 0048xxx -> 48xxx; numery zagraniczne bez zmian.
  Wszystkie raporty (per numer, urzadzenia, krzyzowy) i konsola pokazuja
  numery z prefiksem; wewnetrzne klucze porownan pozostaja kanoniczne.

## 2026-10-14 22:20
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
