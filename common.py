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

def klucz_numer(num) -> str:
    """
    Kanoniczna postac numeru do porownan (klucz w mapach, laczenie billingow).
    0048xxx / +48xxx / 48xxx -> xxx
    """
    n = normalizuj_numer(num)
    if n.startswith("0048") and len(n) > 10:
        n = n[4:]
    elif n.startswith("48") and len(n) > 9:
        n = n[2:]
    return n


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
