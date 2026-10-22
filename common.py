#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wspolne narzedzia dla analizy bilingow (multi-operator)."""
import glob
import os
import re
import readline
import subprocess
import sys

import pandas as pd


# ══════════════════════════════════════════════════════════════════════
# AUTOUZUPEŁNIANIE SCIEZEK (Tab)
# ══════════════════════════════════════════════════════════════════════

class PathCompleter:
    def __init__(self):
        self.matches = []
    def complete(self, text, state):
        if state == 0:
            if text.startswith('~'):
                text = os.path.expanduser(text)
            if os.path.isdir(text) and not text.endswith(os.sep):
                text += os.sep
            self.matches = glob.glob(text + '*')
            if len(self.matches) == 1 and os.path.isdir(self.matches[0]):
                self.matches[0] += os.sep
            self.matches.sort(key=lambda x: (not os.path.isdir(x), x.lower()))
        try:
            return self.matches[state]
        except IndexError:
            return None

def input_path(prompt: str) -> str:
    old_delims = readline.get_completer_delims()
    old_completer = readline.get_completer()
    try:
        readline.set_completer_delims('\t\n;')
        readline.set_completer(PathCompleter().complete)
        readline.parse_and_bind('tab: complete')
        return input(prompt)
    finally:
        readline.set_completer_delims(old_delims)
        readline.set_completer(old_completer)


# ══════════════════════════════════════════════════════════════════════
# PDF -> TEKST
# ══════════════════════════════════════════════════════════════════════

def pdf_to_text(path: str, layout: bool = True) -> str:
    try:
        flag = "-layout" if layout else "-raw"
        result = subprocess.run(["pdftotext", flag, path, "-"],
                                capture_output=True, text=True, check=True)
        return result.stdout
    except FileNotFoundError:
        print("[!] Brak 'pdftotext'. Zainstaluj: sudo apt install poppler-utils")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"[!] Blad pdftotext: {e}")
        sys.exit(1)


# ══════════════════════════════════════════════════════════════════════
# NUMERY — NORMALIZACJA
# ══════════════════════════════════════════════════════════════════════

def normalizuj_numer(num) -> str:
    """Usuwa wszystko poza cyframi."""
    if num is None:
        return ""
    return re.sub(r"\D", "", str(num))

def normalizuj_strone(v) -> str:
    """
    Normalizuje identyfikator strony (numer telefonu): 48123456789 -> 123456789.
    Niecyfrowe identyfikatory przechodza bez zmian. Stosowac na kolumnach
    strona_a/strona_b przy parsowaniu, zeby 48-prefix nie rozdwajal kontaktow.
    """
    n = normalizuj_numer(v)
    if n and n.isdigit() and len(n) >= 9:
        return klucz_numer(n)
    return "" if v is None else str(v).strip()

def klucz_numer(num) -> str:
    """
    Klucz do laczenia numerow (wewnetrzny, porownania, grupowanie).
    Polskie: odcinamy 48 TYLKO gdy wynik to 9 cyfr (pewny numer polski).
    Numery zagraniczne: bez zmian (operator podaje juz z kierunkowym).
    Numery krotkie (4-6 cyfr, SMS specjalne): bez zmian.
    """
    n = normalizuj_numer(num)
    if n.startswith("0048"):
        n = n[4:]
    if n.startswith("48") and len(n) == 11:
        n = n[2:]  # polski numer komorkowy lub stacjonarny z kierunkowym
    return n


def pelny_numer(num) -> str:
    """Pelna postac numeru z prefixem 48 (do wyswietlania w raportach).
    Tylko polskie 9-cyfrowe dostaja 48; zagraniczne, krotkie i nietekstowe
    identyfikatory (np. 'ING') przechodza bez zmian."""
    d = normalizuj_numer(num)
    if not d:
        return str(num).strip()   # nietekstowe identyfikatory (np. 'ING')
    if d.startswith("0048"):
        d = d[4:]
    if len(d) == 9:
        d = "48" + d
    return d



# ══════════════════════════════════════════════════════════════════════
# SKANOWANIE STRUKTURY KATALOGOW
# ══════════════════════════════════════════════════════════════════════
# ROOT/
#   <operator>/<abonent>/...pliki...
# operator = orange | tmobile | plus | play (male litery, dopuszczalne warianty)

ALIASES_OPERATOROW = {
    "orange": "orange", "orangepolska": "orange", "orange_polska": "orange",
    "tmobile": "tmobile", "t-mobile": "tmobile", "t_mobile": "tmobile", "t mobile": "tmobile",
    "plus": "plus", "plusgsm": "plus", "polkomtel": "plus",
    "play": "play", "p4": "play",
}

def znormalizuj_operator(nazwa_folderu: str):
    key = re.sub(r"[\s_]+", "", nazwa_folderu.strip().lower())
    key = key.replace("-", "")
    return ALIASES_OPERATOROW.get(key, None)

def skanuj_dane(root: str, verbose: bool = True):
    """
    Skanuje katalog glowny i zwraca liste rekordow:
        {operator, abonent, folder, pliki: {wykaz, nazwiska, bts}}
    Ignoruje foldery niebedace operatorami i puste podfoldery.
    """
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        print(f"[!] Nie ma takiego katalogu: {root}")
        return []
    znalezione = []
    for poziom1 in sorted(os.listdir(root)):
        folder_op = os.path.join(root, poziom1)
        if not os.path.isdir(folder_op):
            continue
        operator = znormalizuj_operator(poziom1)
        if not operator:
            if verbose:
                print(f"[-] Pominięto (nie rozpoznano operatora): {poziom1}/")
            continue
        for poziom2 in sorted(os.listdir(folder_op)):
            folder_ab = os.path.join(folder_op, poziom2)
            if not os.path.isdir(folder_ab):
                continue
            abonent = poziom2.strip()
            znalezione.append({
                "operator": operator,
                "abonent": abonent,
                "folder": folder_ab,
                "pliki": None,  # wypelniane przez autodetect operatora
            })
    if verbose:
        print(f"[+] Skanowanie {root}: {len(znalezione)} folderow abonentow.")
    return znalezione


# ══════════════════════════════════════════════════════════════════════
# AUTODETEKCJA PLIKOW W FOLDERZE (domyslna — Orange / fallback)
# ══════════════════════════════════════════════════════════════════════

def autodetect_pliki(folder: str):
    """Wykrywa automatycznie pliki Orange w folderze na podstawie wzorca nazwy."""
    wykaz = glob.glob(os.path.join(folder, "*_wykaz.pdf"))
    dane = glob.glob(os.path.join(folder, "*_daneOsobowe.pdf"))
    bts = glob.glob(os.path.join(folder, "*_bts.pdf"))
    return (
        wykaz[0] if wykaz else None,
        dane[0] if dane else None,
        bts[0] if bts else None,
    )


# ══════════════════════════════════════════════════════════════════════
# POMOCNICZE
# ══════════════════════════════════════════════════════════════════════

BLANK = {"", "-", None}
NIE_BTS = BLANK | {"Prz."}
NIE_IMEI = BLANK | {"-", ""}

def _clean_counts(series, wyklucz=BLANK):
    s = series[~series.isin(wyklucz) & series.notna()]
    return s.value_counts()

def _data_min(d):
    return d if d else "0000-00-00"

def _data_max(d):
    return d if d else "9999-99-99"

def klucz_imei(v) -> str:
    """IMEI bazowe = 14 cyfr (TAC+SNR). Cyfra 15 = check, 16 = SVN — to samo urzadzenie."""
    d = normalizuj_numer(v)
    return d[:14]

def klucz_sort_numer(n):
    """Sortowanie numeryczne napisow-cyfr: najpierw dlugosc, potem wartosc."""
    n = str(n)
    return (len(n), n)

def pelne_dane(w) -> bool:
    """Czy wpis zawiera twarde identyfikatory (PESEL/NIP/adres/SIM/krs/regon)."""
    return bool(w.get("pesel") or w.get("nip") or w.get("adres")
                or w.get("sim") or w.get("krs") or w.get("regon"))

def _polacz_nazwy(a, b):
    """
    Polacz dwa teksty informacyjne. Jesli roznia sie tylko ostatnim slowem
    (np. '...nie obslugiwany przez Polkomtel' + '...przez Netia'),
    zwroc jeden tekst z oboma slowami: '...przez Polkomtel i Netia'.
    W przeciwnym razie polacz ' | '.
    """
    if not a:
        return b
    if not b:
        return a
    if a == b:
        return a
    # wspolny prefiks konczacy sie spacja
    i = 0
    for x, y in zip(a, b):
        if x != y:
            break
        i += 1
    pref = a[:i].rsplit(" ", 1)
    if len(pref) == 2 and len(pref[0]) >= 8:
        wa = a[len(pref[0]) + 1:]
        wb = b[len(pref[0]) + 1:]
        if wa and wb and " " not in wa.strip() and " " not in wb.strip():
            # kolejnosc slow KANONICZNA (alfabetyczna) — zawsze ta sama forma,
            # niezaleznie od kolejnosci wierszy w plikach operatora
            w1, w2 = sorted([wa.strip(), wb.strip()])
            return f"{pref[0]} {w1} i {w2}"
    return f"{a} | {b}"

def dedup_historia(wpisy):
    """
    Deduplikacja wpisow historii JEDNEGO numeru (dane z plikow operatora bywaja
    niespojne: ten sam numer w wielu plikach, raz z danymi, raz z komunikatem).
    Regula w pelni sterowana danymi (nic na sztywno):
    - wpis Z DANYMI (nazwa/PESEL/adres) zawsze zostaje,
    - wpis PUSTY zostaje tylko dla okresu NIEPOKRYTEGO zadnym wpisem z danymi.
    """
    if not wpisy:
        return wpisy
    # 1) scal IDENTYCZNE wpisy (te same daty/dane, rozne pliki-zrodla):
    #    zrodla laczymy w jedno pole, wpis zostaje pojedynczy.
    unik = {}
    for w in wpisy:
        k = (w.get("data_akt", ""), w.get("data_dezakt", ""),
             w.get("nazwa", ""), w.get("pesel", ""), w.get("nip", ""),
             w.get("adres", ""), w.get("sim", ""))
        if k in unik:
            z, nz = unik[k].get("zrodlo", ""), w.get("zrodlo", "")
            if nz and nz not in z:
                unik[k]["zrodlo"] = (z + " | " + nz).strip(" |")
        else:
            unik[k] = dict(w)
    wpisy = list(unik.values())
    if not wpisy:
        return wpisy
    # "Wpis z danymi" = ma TWARDY identyfikator (PESEL/NIP/adres/SIM/krs/regon).
    # Samo pole nazwy NIE wystarcza — operator umieszcza tam czasem komunikaty
    # typu "numer nie obslugiwany przez <siec>" (kryterium nadal sterowane danymi,
    # bez sztywnych nazw sieci).
    def ma_dane(w):
        return bool(w.get("pesel") or w.get("nip") or w.get("adres")
                    or w.get("sim") or w.get("krs") or w.get("regon"))
    twarde = [w for w in wpisy if ma_dane(w)]
    # wpisy bez twardych identyfikatorow: pogrupuj po okresie — te same daty
    # z roznymi tekstami (np. odpowiedz z dwoch baz operatora: Polkomtel+Netia)
    # scal w jeden wpis z polaczonym tekstem
    puste = [w for w in wpisy if not ma_dane(w)]
    grupy = {}
    for w in puste:
        grupy.setdefault((w.get("data_akt", ""), w.get("data_dezakt", "")), []).append(w)
    for (od, do), g in grupy.items():
        if len(g) == 1:
            continue
        baza = dict(g[0])
        zrodla = []
        for w in g:
            z = w.get("zrodlo", "")
            if z and z not in zrodla:
                zrodla.append(z)
        baza["nazwa"] = ""
        for w in g:
            baza["nazwa"] = _polacz_nazwy(baza["nazwa"], w.get("nazwa", ""))
        if zrodla:
            baza["zrodlo"] = " | ".join(zrodla)
        for w in g:
            puste.remove(w)
        puste.append(baza)

    if twarde:
        pelne = twarde
    else:
        # zadnego twardego identyfikatora — fallback: traktuj (scalona) nazwe jako dane
        pelne = list(puste)
        puste = []
    if not pelne:
        return wpisy

    out = list(pelne)
    for w in puste:
        od, do = _data_min(w.get("data_akt", "")), _data_max(w.get("data_dezakt", ""))
        pokryty = any(
            not (do < _data_min(p.get("data_akt", "")) or od > _data_max(p.get("data_dezakt", "")))
            for p in pelne)
        if not pokryty:
            out.append(w)
    return sorted(out, key=lambda w: _data_min(w.get("data_akt", "")))

def fmt_czas(sekundy):
    if pd.isna(sekundy) or sekundy == 0:
        return "0d 0g 00m 00s"
    s = int(sekundy)
    d = s // 86400
    s %= 86400
    h = s // 3600
    s %= 3600
    m = s // 60
    sec = s % 60
    return f"{d}d {h}g {m:02d}m {sec:02d}s"

def okres_bilingow(df):
    if df.empty:
        return "", ""
    return df["data"].min(), df["data"].max()

def dane_abonenta(target, nazwiska_map):
    dane = nazwiska_map.get(klucz_numer(target), {})
    return {
        "nazwa": dane.get("nazwa", ""),
        "adres": dane.get("adres", ""),
        "pesel": dane.get("pesel", ""),
    }


# ══════════════════════════════════════════════════════════════════════
# OGLĘDZINY — LISTING PLIKÓW Z SHA-256
# ══════════════════════════════════════════════════════════════════════

def _rozmiar_pliku(bajty):
    if bajty >= 1 << 30:
        return f"{bajty / (1 << 30):.1f} GB ({bajty} B)"
    if bajty >= 1 << 20:
        return f"{bajty / (1 << 20):.1f} MB ({bajty} B)"
    if bajty >= 1 << 10:
        return f"{bajty / (1 << 10):.1f} KB ({bajty} B)"
    return f"{bajty} B"


def listing_folderu(folder):
    """Listing wszystkich plikow zrodlowych w folderze abonenta z suma SHA-256
    i rozmiarem (B/KB/MB/GB + bajty). Oględzinom poddaje sie cala przesylke —
    kazdy raport wymienia wszystkie pliki z folderu. Zwraca (nazwa, sha, rozmiar)."""
    import hashlib
    rozszerzenia = ('.xls', '.xlsx', '.pdf', '.csv', '.txt', '.docx')
    pliki = []
    try:
        for fn in sorted(os.listdir(folder)):
            p = os.path.join(folder, fn)
            if not os.path.isfile(p):
                continue
            if not fn.lower().endswith(rozszerzenia):
                continue
            h = hashlib.sha256()
            with open(p, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    h.update(chunk)
            pliki.append((fn, h.hexdigest(), _rozmiar_pliku(os.path.getsize(p))))
    except Exception:
        pass
    return pliki


def preambula_ogledzin(operator_nazwa, cel_txt, okres_od, okres_do,
                       folder_abonenta, pliki):
    """Preambula oględzin danych telekomunikacyjnych — lista linii tekstu.
    Wstawiana przed dotychczasowa trescia raportu (DOCX: akapity + page break;
    XLSX: pierwsze wiersze arkusza)."""
    L = []
    L.append("=" * 100)
    L.append("  OGLĘDZINY DANYCH TELEKOMUNIKACYJNYCH")
    L.append("=" * 100)
    L.append(f"  Oględzinom poddano dane telekomunikacyjne dostarczone przez operatora {operator_nazwa}")
    L.append(f"  dla {cel_txt} za okres od {okres_od} do {okres_do}.")
    L.append(f"  Dane umieszczono w folderze abonenta '{os.path.basename(folder_abonenta)}'.")
    L.append("")
    L.append("  PLIKI ZRODLOWE (listing z sumami kontrolnymi SHA-256):")
    L.append("  {:>3}  {:<50}  {}".format("Lp", "Plik", "SHA-256"))
    L.append("  " + "-" * 96)
    if pliki:
        for i, (nazwa, sha) in enumerate(pliki, 1):
            L.append("  {:>3}  {:<50}  {}".format(i, nazwa[:50], sha))
    else:
        L.append("  (brak rozpoznawalnych plikow zrodlowych w folderze abonenta)")
    L.append("")
    return L


# Teksty informacyjne operatora (obsługiwany/nieobsługiwany, nie znaleziono) — skracamy
_RE_TEKST_OBSLUGI = re.compile(r"obs[lł]ugiwany|znalezion[oy]", re.IGNORECASE)

def czytelna_nazwa(nazwa):
    """Nazwa kontaktu do wyswietlenia: dane osobowe gdy operator je podaje;
    komunikat typu 'numer nie obslugiwany przez <siec>' -> 'brak danych';
    brak nazwy -> 'brak danych' (ujednolicone)."""
    if nazwa is None:
        return "brak danych"
    n = str(nazwa).strip().strip('"')
    if not n or n.lower() == "nan":
        return "brak danych"
    if _RE_TEKST_OBSLUGI.search(n):
        return "brak danych"
    return n


def preambula_zbiorcza(rekordy):
    """Oględziny dla raportu zbiorczego: listing WSZYSTKICH folderow abonentow
    z plikami i SHA-256. Zwraca liste wierszy (kazdy wiersz = lista komorek)
    gotowa do wstawienia w TXT (join) i XLSX (append)."""
    L = []
    L.append(["=" * 100])
    L.append(["OGLĘDZINY DANYCH TELEKOMUNIKACYJNYCH"])
    L.append(["=" * 100])
    L.append([f"Oględzinom poddano dane telekomunikacyjne {len(rekordy)} analizowanych abonentow."])
    L.append([""])
    seen = set()
    lp = 1
    for r in rekordy:
        folder = r.get("folder")
        if not folder or folder in seen:
            continue
        seen.add(folder)
        L.append([f"FOLDER: {r.get('operator','')}/{os.path.basename(folder)}"])
        pliki = listing_folderu(folder)
        if pliki:
            L.append(["Lp", "Plik", "SHA-256", "Rozmiar"])
            for nazwa, sha, roz in pliki:
                L.append([str(lp), nazwa, sha, roz])
                lp += 1
        else:
            L.append(["(brak rozpoznawalnych plikow zrodlowych w folderze)"])
        L.append([""])
    return L


# ─────────────────────────────────────────────────────────────────────
# INTELIGENTNE SZEROKOSCI KOLUMN
# ─────────────────────────────────────────────────────────────────────
# Cap = maksymalna szerokosc kolumny w znakach, wg naglowka kolumny.
# Kolumny liczbowe/daty waskie; tekst (nazwy/adresy) zawija sie w komorce.
CAPY_KOLUMN = {
    "lp": 6, "w": 5, "p": 5, "pr": 5, "razem": 8,
    "wychodzace": 11, "przychodzace": 11,
    "sms": 8, "polaczenia": 12, "dane kontaktu": 20,
    "od": 11, "do": 11, "okres od": 11, "okres do": 11, "zakres czasu": 24,
    "data": 12, "czas": 9,
    "numer": 15, "numer telefonu": 15, "numer kontaktu": 15,
    "numer abonenta": 13, "numer drugiego abonenta": 13, "numer (msisdn)": 13,
    "abonent": 35, "nazwa": 35, "nazwa / firma": 35, "nazwa kontaktu": 35,
    "adres": 40, "adres stacji": 40,
    "kod bts": 13, "inicjujace": 11, "odbierajace": 11, "liczba polaczen": 12,
    "imei": 17, "imei (baza 14 cyfr)": 17, "imsi": 17,
    "adres ip": 42, "ip": 42,
    "liczba zdarzen": 12, "liczba sesji": 10, "liczba abonentow": 12,
    "czas wych": 15, "czas przych": 15, "laczny czas": 15,
    "sha-256": 66, "rozmiar": 20, "plik": 55,
    "operator": 13, "folder abonenta": 28,
    "pesel/regon": 13, "pesel/nip-krs": 14, "pesel/nip od": 14, "pesel/nip do": 14,
    "voice przych": 10, "voice wych": 10,
    "proby przych": 10, "proby wych": 10,
    "sms przych": 10, "sms wych": 10,
    "fwd przych": 10, "fwd wych": 10, "dane": 7, "data_": 7,
    "ta sama osoba/firma": 10, "z innymi": 9, "z kontakt.": 10,
    "zd.z kont.": 11, "zdarzen z kontaktem": 14,
    "status": 10, "zrodlo": 40,
}

def cap_kolumny(naglowek) -> int:
    """Cap szerokosci kolumny w znakach, na podstawie tekstu naglowka."""
    return CAPY_KOLUMN.get(str(naglowek).strip().lower(), 30)
