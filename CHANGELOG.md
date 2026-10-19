# CHANGELOG — Biling Toolkit
Format wersji: RRRR-MM-DD GG:MM (data godzina:minuty)

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
