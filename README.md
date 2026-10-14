# Biling Toolkit — analiza bilingow multi-operator
WERSJA: 2026-10-14 14:55  (format wersji: RRRR-MM-DD GG:MM)

## CEL PROJEKTU
Narzedzie do analizy bilingow od 4 operatorow (Orange, T-Mobile, Plus, Play),
dostarczanych w roznych formatach, z dwoma poziomami analizy:
1. RAPORT PER NUMER — klasyczna analiza dla danego MSISDN (kontakty, SMS, internet, BTS, IMEI, historia abonenta),
2. ANALIZA KRZYZOWA — laczenie abonentow ze soba: komunikacja bezposrednia, wspolne kontakty osob trzecich, wspolne urzadzenia.

## KLUCZE IDENTYFIKACYJNE (zasada obowiazujaca dla KAZDEGO operatora)
1. **MSISDN (numer telefonu)** — klucz podstawowy. Laczy billingi z roznych operatorow i zrodel.
   - numer polski: `48123456789` -> klucz `123456789` (odcinamy 48/0048),
   - numer zagraniczny: przechodzi bez zmian (np. `79774264845`).
2. **PESEL** (osoba) lub **NIP/KRS** (firma) — klucz wtorny. Ten sam uzytkownik moze miec
   KILKA numerow — klucz wtorny je laczy w jedna osobe/firme w raporcie zbiorczym.
3. **Imie i nazwisko / nazwa NIGDY nie sa kluczem** — moga byc wpisane z bledem lub falszywe.
   Sa wyswietlane w raportach, ale dopasowan na ich podstawie NIE robimy.

## CO JEST ZROBIONE
### Architektura
- [x] Kanoniczny format danych (kolumny: data, czas, czas_trwania, typ, strona_a/b, bts_a/b, imei_a/b, imsi_a/b)
- [x] Normalizacja numerow `klucz_numer()` (polskie 48/0048 odcinane, zagraniczne bez zmian)
- [x] Struktura `input/<operator>/<abonent>/`, autodetekcja operatora po nazwie folderu
- [x] Auto-skan `./input` w obu skryptach (bez podawania sciezek)
- [x] `analizaBilling.py` — raport klasyczny per numer (TXT+CSV)
- [x] `analizaKrzyzowa.py` — analiza krzyzowa: sekcje A (abonenci), B (komunikacja bezposrednia),
      C (osoby trzecie laczace abonentow), D (wspolne IMEI)
- [x] Scalanie zrodel po MSISDN (te sama osoba w wielu plikach/zapytaniach -> jeden rekord)
- [x] Identyfikator PESEL/NIP-KRS w raportach + flaga "ta sama osoba/firma" dla par numerow

### Parsery operatorow
- [x] ORANGE (PDF) — pelny: wykaz polaczen, dane osobowe (historia zmian), BTS
- [x] PLUS (Polkomtel) — Excel .xls/.xlsx: naglowek wyszukiwany dynamicznie (wiersz "Parametr"),
       numer abonenta z sekcji "Parametry zadania", typy MOC/PTC/POC/MTC/SMO/SMT/MMR/UCAT/UCAM/FORW
       mapowane na VOICE/SMS/MMS/PRÓBA/FWD, dane abonenckie (PESEL, NIP, Ważne od/do) jako
       nazwiska+historia, transmisja danych jako DATA, adres BTS wprost w rekordach,
       zestawy grupowane po ID zapytania, pliki bez wierszy danych obslugiwane
- [ ] T-MOBILE — szkielet (autodetekcja), parser do napisania po dostarczeniu przykladu
- [ ] PLAY — szkielet (autodetekcja), parser do napisania po dostarczeniu przykladu

## DO ZROBIENIA
- [ ] Parsery T-Mobile i Play (czeka na przykladowe pliki)
- [ ] Weryfikacja parsera Plus na pliku z realnymi danymi (kierunek A/B, czas trwania, typy)
- [ ] Rozbicie zbiorczego billingu Plus na wiele numerow (jesli parametr obejmuje kilka MSISDN)
- [ ] Grupowanie w raporcie zbiorczym po kluczu wtornym (osoba/firma = kilka numerow w jednym wierszu)
- [ ] Mozliwy eksport grafu polaczen (CSV/GEXF)

## STRUKTURA KATALOGOW
    input/
    ├── orange/<abonent>/   xxx_wykaz.pdf, xxx_daneOsobowe.pdf, xxx_bts.pdf
    ├── plus/<abonent>/     *-wyniki-*-wykaz_polaczen-*.xls (+ dane_abonenckie, transmisja_danych)
    ├── tmobile/<abonent>/  (parser w przygotowaniu)
    └── play/<abonent>/     (parser w przygotowaniu)
Kazdy abonent = osobny podfolder o DOWOLNEJ nazwie. Operator wykrywany automatycznie.

## UZYCIE
    python3 analizaKrzyzowa.py     # analiza wszystkiego z ./input (raporty per numer + zbiorczy)
    python3 analizaBilling.py      # wykryje ./input, zapytai o analize krzyzowa lub reczny wybor
    python3 analizaBilling.py --folder input/plus/<abonent>   # pojedynczy folder
Wymagania: python3, pandas, pdftotext (poppler-utils), xlrd (.xls), openpyxl (.xlsx).

## HISTORIA ZMIAN — szczegoly w CHANGELOG.md
- 2026-10-14 14:55 — klucze PESEL/NIP-KRS, scalanie po MSISDN, parser Plus przetestowany na plikach QR
