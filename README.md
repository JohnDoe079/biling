# Biling Toolkit — analiza bilingow multi-operator
WERSJA: 2026-10-14 21:09  (format wersji: RRRR-MM-DD GG:MM)

## CEL PROJEKTU
Narzedzie do analizy bilingow od 4 operatorow (Orange, T-Mobile, Plus, Play),
dostarczanych w roznych formatach, z dwoma poziomami analizy:
1. RAPORT PER NUMER — klasyczna analiza dla danego MSISDN (kontakty, SMS, internet, BTS, IMEI, historia abonenta),
2. ANALIZA KRZYZOWA — laczenie abonentow ze soba: komunikacja bezposrednia, wspolne kontakty osob trzecich, wspolne urzadzenia.

## DANE WRAŻLIWE
NIGDZIE w projekcie (kod, komentarze, README, CHANGELOG, przykłady) NIE umieszczamy
danych wrażliwych: nazwisk, adresów, numerów telefonów, PESEL, IMEI, IMSI.
Wylacznie maskowane placeholdery (np. 48XXXXXXXXX, XXXXXXXXXXX).

## KLUCZE IDENTYFIKACYJNE (zasada obowiazujaca dla KAZDEGO operatora)
1. **MSISDN (numer telefonu)** — klucz podstawowy. Laczy billingi z roznych operatorow i zrodel.
   - numer polski: `48XXXXXXXXX` -> klucz `XXXXXXXXX` (odcinamy 48/0048),
   - numer zagraniczny: przechodzi bez zmian (np. `XXXXXXXXXXX`).
   Prezentacja (common.format_numer): numery wyswietlane Z prefiksem krajowym,
   ale 48 TYLKO dla numerow polskich: 9 cyfr zaczynajacych sie od 2-8
   (komorkowy lub stacjonarny) -> doklejamy 48; 9 cyfr od 0/1/9 zostaje
   bez zmian (nie wyglada na polski).
2. **PESEL** (osoba) lub **NIP/KRS** (firma) — klucz wtorny. Ten sam uzytkownik moze miec
   KILKA numerow — klucz wtorny je laczy w jedna osobe/firme w raporcie zbiorczym.
3. **Imie i nazwisko / nazwa NIGDY nie sa kluczem** — moga byc wpisane z bledem lub falszywe.
   Sa wyswietlane w raportach, ale dopasowan na ich podstawie NIE robimy.
   Uwaga: operator podaje dane abonenckie tylko ze swojej sieci — kontakty
   bedace analizowanymi numerami z innych sieci uzupelniamy z ich folderow.

## CO JEST ZROBIONE
### Architektura
- [x] Kanoniczny format danych (kolumny: data, czas, czas_trwania, typ, strona_a/b, bts_a/b, imei_a/b, imsi_a/b)
- [x] Normalizacja numerow `klucz_numer()` (polskie 48/0048 odcinane, zagraniczne bez zmian)
- [x] Struktura `input/<operator>/<abonent>/`, autodetekcja operatora po nazwie folderu
- [x] Auto-skan `./input` w obu skryptach (bez podawania sciezek)
- [x] `analizaBilling.py` — ORCHESTRATOR: raport per numer + automatyczna analiza krzyzowa dla >1 numeru,
      ZERO pytan interaktywnych (operator z nazwy folderu, pliki autowykrywane)
- [x] `analizaKrzyzowa.py` — analiza krzyzowa: sekcja A (OSOBY/FIRMY grupowane
      po PESEL/NIP-KRS: numery, operatorzy, IMEI), A2 (wykaz numerow),
      B (komunikacja miedzy osobami), C (osoby trzecie), D (wspolne IMEI)
- [x] Scalanie zrodel po MSISDN (ta sama osoba w wielu plikach/zapytaniach -> jeden rekord)
- [x] Identyfikator PESEL/NIP-KRS w raportach + flaga "ta sama osoba/firma" dla par numerow
- [x] Tryb URZADZENIA (IMEI): autodetekcja zestawow kluczowanych po IMEI; raport urzadzenia
      pokazuje jakie MSISDN byly uzywane w telefonie (z IMSI, okresem, kontaktami, BTS)
- [x] Raport ZAWSZE per numer — rowniez gdy dane sa puste (numer nie wystepuje u operatora)
      lub parser operatora nie istnieje (raport-zalacznik z informacja)
- [x] Zestaw z samymi danymi abonenckimi (zapytanie po karcie SIM) obslugiwany;
      w raporcie: SIM, forma (pre-paid/NPLAN), status karty, okres waznosci
- [x] Preambula oględzin w kazdym raporcie: formulka + listing plikow z SHA-256
- [x] Sekcja 5: IMSI obok IMEI (najczestsza karta SIM w urzadzeniu)
- [x] Konsola: podsumowanie wykrytych zestawow (folder, numer/IMEI, rekordy, okres)
      + lista wykrytych numerow MSISDN i urzadzen IMEI
- [x] Porownania numerow kanonikalizowane (48xxx -> xxx) — naprawia puste sekcje dla Plus

### Parsery operatorow
- [x] ORANGE (PDF) — pelny: wykaz polaczen, dane osobowe (historia zmian), BTS
- [x] PLUS (Polkomtel) — Excel .xls/.xlsx: naglowek wyszukiwany dynamicznie (wiersz "Parametr"),
       numer abonenta z sekcji "Parametry zadania", typy MOC/PTC/POC/MTC/SMO/SMT/MMR/UCAT/UCAM/FORW
       mapowane na VOICE/SMS/MMS/PRÓBA/FWD, dane abonenckie (PESEL, NIP, SIM, Typ MSISDN, Status,
       Ważne od/do) jako nazwiska+historia, transmisja danych jako DATA, adres BTS wprost w rekordach,
       zestawy grupowane po ID zapytania, pliki bez wierszy danych obslugiwane
- [ ] T-MOBILE — szkielet (autodetekcja), parser do napisania po dostarczeniu przykladu
- [ ] PLAY — szkielet (autodetekcja), parser do napisania po dostarczeniu przykladu

## DO ZROBIENIA
- [ ] Parsery T-Mobile i Play (czeka na przykladowe pliki)
- [ ] Rozbicie zbiorczego billingu Plus na wiele numerow (jesli parametr obejmuje kilka MSISDN)
- [ ] Grupowanie w raporcie zbiorczym po kluczu wtornym (osoba/firma = kilka numerow w jednym wierszu)
- [ ] Mozliwy eksport grafu polaczen (CSV/GEXF)
- [ ] Wspolne urzadzenia (IMEI) liczone per MSISDN wewnatrz zestawow kluczowanych po IMEI
      (obecnie liczone per rekord) — przy analizie podobienstw

## STRUKTURA KATALOGOW
    input/
    ├── orange/<abonent>/   xxx_wykaz.pdf, xxx_daneOsobowe.pdf, xxx_bts.pdf
    ├── plus/<abonent>/     *-wyniki-*-wykaz_polaczen-*.xls (+ dane_abonenckie, transmisja_danych)
    ├── tmobile/<abonent>/  (parser w przygotowaniu)
    └── play/<abonent>/     (parser w przygotowaniu)
Kazdy abonent = osobny podfolder o DOWOLNEJ nazwie. Operator wykrywany automatycznie.
Raporty trafiaja do podfolderu <outdir>/RRRR-MM-DD_GGMM (data i godzina uruchomienia).

## UZYCIE
    python3 analizaBilling.py                      # ORCHESTRATOR: ./input -> ./raport_bilingow
                                                   # raporty per numer (CSV) + analiza krzyzowa (>1 numer)
    python3 analizaBilling.py --txt                # raporty dodatkowo w TXT
    python3 analizaBilling.py --numer 48XXXXXXXXX  # tylko jeden numer / IMEI
    python3 analizaBilling.py --bez-krzyzowej      # wylacz analize krzyzowa
    python3 analizaBilling.py --dane ./in --outdir ./out
    python3 analizaKrzyzowa.py                     # tylko analiza krzyzowa (raport zbiorczy)
Wymagania: python3, pandas, pdftotext (poppler-utils), xlrd (.xls), openpyxl (.xlsx),
python-docx (raporty DOCX, opcjonalnie: pip install python-docx).

## HISTORIA ZMIAN — szczegoly w CHANGELOG.md
- 2026-10-14 18:51 — preambula oględzin (formulka + listing plikow z SHA-256), IMSI obok IMEI
- 2026-10-14 16:42 — prefiks 48 tylko dla polskich numerow (9 cyfr od 2-8; 0/1/9 bez zmian)
- 2026-10-14 16:34 — numery prezentowane z prefiksem krajowym 48 (9 cyfr bez prefiksu = polski numer)
- 2026-10-14 16:20 — orchestrator bez pytan, raporty urzadzen (IMEI), dane SIM (forma/status), raporty CSV-domyslnie
- 2026-10-14 14:55 — klucze PESEL/NIP-KRS, scalanie po MSISDN, parser Plus przetestowany na plikach QR
