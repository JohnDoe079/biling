# Biling Toolkit — analiza bilingow multi-operator
WERSJA: 2026-10-12 11:12

## CO JEST ZROBIONE (stan na 2026-10-12 11:12)

### Architektura
- [x] Kanoniczny format danych (kolumny jak w Orange: data, czas, czas_trwania, typ, strona_a/b, bts_a/b, imei_a/b, imsi_a/b)
- [x] Normalizacja numerow `klucz_numer()` (usuwa +48/48/0048 — laczenie billingow z roznych operatorow)
- [x] Skanowanie struktury `input/<operator>/<abonent>/` z autodetekcja operatora po nazwie folderu
       (aliasy: orange/orangepolska, tmobile/t-mobile/t_mobile, plus/polkomtel/plusgsm, play/p4)
- [x] `analizaBilling.py` — klasyczny raport per numer (TXT+CSV): kontakty glosowe+proby, SMS/MMS,
       internet, BTS, IMEI, historia zmian abonenta z podzialem na okresy
- [x] `analizaKrzyzowa.py` — analiza krzyzowa wielu abonentow:
  - sekcja A: lista analizowanych abonentow
  - sekcja B: komunikacja bezposrednia miedzy abonentami (kto sie z kim laczyl)
  - sekcja C: osoby trzecie laczace pary abonentow (wspolne kontakty)
  - sekcja D: wspolne urzadzenia (IMEI) w billingach roznych abonentow

### Parsery operatorow
- [x] ORANGE (PDF) — pelny: wykaz polaczen, dane osobowe (z historia zmian), BTS
- [~] PLUS (Polkomtel) — Excel .xls/.xlsx, naglowek w wierszu 5; parser wykazu zrobiony
       (kolumny: poczatek, koniec, parametr, a/b msisdn, a/b bts address; typ domyslnie VOICE;
       IMEI/IMSI puste). DO POTWIERDZENIA na realnych danych.
- [ ] T-MOBILE — szkielet (autodetekcja plikow), parser do napisania
- [ ] PLAY — szkielet (autodetekcja plikow), parser do napisania

## DO ZROBIENIA
- [ ] Parser T-Mobile (potrzebny przykladowy plik)
- [ ] Parser Play (potrzebny przykladowy plik)
- [ ] Ustalenie typow zdarzen w Plusie (czy jest kolumna typu? domyslnie VOICE)
- [ ] parse_nazwiska / parse_bts dla Plusa, T-Mobile, Play
- [ ] Rozbicie zbiorczego pliku Plusa na wiele numerow (parametr) na osobne rekordy abonentow
- [ ] Mozliwe: eksport mapy polaczen (graf) do CSV/GEXF

## STRUKTURA KATALOGOW (input/)

    input/
    ├── orange/           <- podfoldery abonentow Orange (PDF)
    │   └── <nazwa_abonenta>/
    │       ├── xxx_wykaz.pdf
    │       ├── xxx_daneOsobowe.pdf   (opcjonalnie)
    │       └── xxx_bts.pdf           (opcjonalnie)
    ├── plus/             <- podfoldery abonentow Plus (Excel .xls/.xlsx)
    │   └── <nazwa_abonenta>/
    │       └── billing.xlsx
    ├── tmobile/          <- (parser w przygotowaniu)
    └── play/             <- (parser w przygotowaniu)

Kazdy abonent = osobny podfolder o DOWOLNEJ nazwie (nazwisko / firma / numer).
Skrypt sam wykrywa operatora po nazwie folderu pierwszego poziomu — NIE trzeba nic wybierac.

## UZYCIE

    # analiza krzyzowa wszystkich abonentow z input/ (raporty per numer + raport zbiorczy):
    python3 analizaKrzyzowa.py --dane input --outdir raport_krzyzowy

    # tryb interaktywny:
    python3 analizaKrzyzowa.py

    # pojedynczy numer / pojedynczy folder (tryb klasyczny):
    python3 analizaBilling.py --folder input/orange/<abonent>

Wymagania: python3, pandas, pdftotext (sudo apt install poppler-utils), xlrd (dla .xls), openpyxl (dla .xlsx).

## HISTORIA ZMIAN
- 2026-10-12 11:12 — v2: struktura input/, parser Plus (Excel), analiza krzyzowa, README, wersjonowanie
- wczesniej  — v1: tylko Orange, tryb pojedynczego numeru
