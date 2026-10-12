#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parsery dla operatora Orange Polska."""
import re

import pandas as pd

from common import pdf_to_text, normalizuj_numer, klucz_numer, autodetect_pliki


# ══════════════════════════════════════════════════════════════════════
# WYKAZ POŁACZEN
# ══════════════════════════════════════════════════════════════════════

_ORANGE_RP_TOKENS = [
    "PRÓBA_SMSW", "PRÓBA_SMSD", "BLOK_SMSW", "BLOK_SMSD", "BLOK_VOICE",
    "PRÓBA", "VOICE", "DATA", "SMS", "MMS", "FWD", "VIDEO", "ViLTE",
    "ViWiFi", "RTT", "ROAMING", "VoIP",
]
_ORANGE_RP_TOKENS.sort(key=len, reverse=True)
_ORANGE_LINE_RE = re.compile(
    r"^\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})\s+(?:(\d+)\s+)?("
    + "|".join(re.escape(t) for t in _ORANGE_RP_TOKENS) + r")\s+(.+)$"
)
_ORANGE_SKIP = (
    "Nasz znak", "Opis dostepny", "Strona", "Koniec Wykazu",
    "1. POŁACZENIA", "OKRES", "Kierunek:", "Rodzaje polaczen", "MSISDN",
    "DATA CZAS", "Legenda", "DATA -", "CZAS -", "RP -", "RP ",
    "IDENTYFIKATOR", "BTS A", "BTS B", "IMEI A", "IMEI B", "IMSI A",
    "IMSI B", "NUMER B", "Zapis", "Powyzej", "VIDEO -", "BLOK_SMSW/",
    "BLOK_VOICE -", "RTT ", "Wykaz", "POŁACZENIA", "OKRES:",
    "Wykaz polaczen", "Wykaz przekazow", "Wykaz wiadomosci",
    "DANE BTS", "AZYM", "KAT", "DŁUGOSC", "SZEROKOSC", "ZASIEG",
    "SEKTOR", "MIEJSCOWOSC", "ULICA", "WOJ", "URUCHOMIENIA", "WYLACZENIA",
    "DANE OSOBOWE", "IDENTYFIKATOR UZYTKOWNIKA", "OPER", "RU", "RU 2",
    "DATA AKT", "DATA DEZAKT", "TYP", "ABONENT", "PESEL", "REGON",
    "KOD", "MIASTO", "GŁOWNY", "Przeniesiony do innego operatora",
)

def parse_orange(path: str, verbose: bool = False):
    rows, fails, msisdn = [], [], None
    text = pdf_to_text(path)
    lines = text.split("\n")
    for line in lines[:100]:
        m = re.search(r"MSISDN\s+(\d+)", line)
        if m:
            msisdn = m.group(1)
            break
    for line in lines:
        s = line.strip()
        if not s or s.startswith(_ORANGE_SKIP):
            continue
        m = _ORANGE_LINE_RE.match(line)
        if not m:
            fails.append(s)
            continue
        date, czas, czas_trwania, typ, rest = m.groups()
        tokens = rest.split()
        if len(tokens) < 8:
            fails.append(s)
            continue
        bts_a, imei_a, imsi_a, numer_b, bts_b, imei_b, imsi_b = tokens[-7:]
        identyfikator = " ".join(tokens[:-7])
        rows.append(dict(
            data=date, czas=czas,
            czas_trwania=int(czas_trwania) if czas_trwania else None,
            typ=typ, strona_a=identyfikator, bts_a=bts_a, imei_a=imei_a,
            imsi_a=imsi_a, strona_b=numer_b, bts_b=bts_b, imei_b=imei_b,
            imsi_b=imsi_b,
        ))
    df = pd.DataFrame(rows)
    if verbose and fails:
        print(f"[orange] nie sparsowano {len(fails)} linii:")
        for f in fails[:10]:
            print("   ", f)
    return df, msisdn




# ══════════════════════════════════════════════════════════════════════
# AUTODETEKCJA PLIKOW W FOLDERZE ABONENTA
# ══════════════════════════════════════════════════════════════════════

def autodetect(folder: str):
    wykaz, nazwiska, bts = autodetect_pliki(folder)
    return {"wykaz": wykaz, "nazwiska": nazwiska, "bts": bts}

def datasets(folder: str):
    """Jeden zestaw na folder Orange."""
    d = autodetect(folder)
    return [{"token": None, "wykaz": d["wykaz"], "nazwiska": d["nazwiska"],
             "transmisja": None, "bts": d["bts"]}]


# ══════════════════════════════════════════════════════════════════════
# DANE OSOBOWE / NAZWISKA  — TOKENOWY PARSER ZE SCALANIEM
# ══════════════════════════════════════════════════════════════════════

def parse_orange_nazwiska(path: str, verbose: bool = False) -> tuple:
    """
    Zwraca (mapping, historia).
    Uzywa pdftotext BEZ -layout (latwiejsza tokenizacja).
    """
    mapping = {}
    historia = {}
    # BEZ -layout - wiersze sa krotsze i latwiejsze do tokenizacji
    text = pdf_to_text(path, layout=False)
    text = text.replace('"', '')  # usun cudzyslowy
    lines = text.split("\n")

    re_data = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    re_kod = re.compile(r'^\d{2}-\d{3}$')
    re_lp_num = re.compile(r'^\s*(\d+)\s+(\d{9,12})\b')

    # --- FAZA 1: scalanie linii w pelne rekordy ---
    records = []
    current = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if re_lp_num.match(s):
            if current:
                records.append(" ".join(current))
            current = [s]
        else:
            if current:
                current.append(s)
    if current:
        records.append(" ".join(current))

    if verbose:
        print(f"[orange_nazwiska] scalono {len(records)} rekordow.")

    # --- FAZA 2: parsowanie kazdego scalonego rekordu ---
    for rec in records:
        tokens = rec.split()
        m = re_lp_num.match(rec)
        if not m:
            continue

        lp, numer = m.group(1), m.group(2)
        numer_norm = klucz_numer(numer)

        # Znajdz wszystkie daty
        daty_idx = [idx for idx, t in enumerate(tokens) if re_data.match(t)]
        data_akt = ""
        data_dezakt = ""

        # Znajdz kod pocztowy
        kod_idx = None
        for idx, t in enumerate(tokens):
            if re_kod.match(t):
                kod_idx = idx
                break

        # Znajdz PESEL/REGON
        pesel_idx = None
        if kod_idx is not None:
            # PESEL/REGON jest bezposrednio przed kodem (lub 1-2 tokeny przed)
            for i in range(kod_idx - 1, max(kod_idx - 5, -1), -1):
                if i < 2:
                    break
                t = tokens[i]
                # pomin daty i same litery (TYP)
                if re_data.match(t) or (len(t) == 1 and t.isalpha()):
                    continue
                # PESEL/REGON to token z cyframi, nie kod
                if re.search(r'\d', t) and not re_kod.match(t):
                    pesel_idx = i
                    break
        else:
            # Brak kodu - szukamy PESEL/REGON od konca
            for i in range(len(tokens) - 1, max(len(tokens) - 6, -1), -1):
                if i < 2:
                    break
                t = tokens[i]
                if re_data.match(t) or re_kod.match(t):
                    continue
                if re.search(r'\d', t):
                    # Upewnij sie ze to nie jest czesc adresu (np. "10", "32A")
                    # PESEL/REGON ma min 5 znakow i zawiera wiecej cyfr niz liter
                    if len(t) >= 5 and sum(c.isdigit() for c in t) >= 5:
                        pesel_idx = i
                        break

        # Wyciagnij nazwe (ABONENT)
        nazwa = ""
        if daty_idx:
            last_date = daty_idx[-1]
            start = last_date + 1

            # Pomin TYP (1 litera: T, B, I)
            if start < len(tokens) and len(tokens[start]) == 1 and tokens[start].isalpha():
                start += 1

            # "Przeniesiony do innego operatora" jako nazwa
            if start < len(tokens) and tokens[start] == "Przeniesiony":
                nazwa = "numer u innego operatora"
                start = len(tokens)  # koniec

            end = pesel_idx if pesel_idx is not None else len(tokens)

            if start < end:
                candidate = tokens[start:end]
                # Jesli candidate to same cyfry -> puste (brak danych abonenta)
                if candidate and all(t.isdigit() for t in candidate):
                    nazwa = ""
                else:
                    nazwa = " ".join(candidate)

        # Wyciagnij adres
        adres = ""
        pesel = ""
        if pesel_idx is not None:
            pesel = tokens[pesel_idx]
        if kod_idx is not None and kod_idx + 1 < len(tokens):
            kod = tokens[kod_idx]
            miasto = tokens[kod_idx + 1]
            ulica_tokens = []
            for t2 in tokens[kod_idx + 2:]:
                if re.search(r'\d', t2) and len(t2) >= 5 and sum(c.isdigit() for c in t2) >= 5:
                    break  # kolejny PESEL/REGON
                ulica_tokens.append(t2)
            ulica = " ".join(ulica_tokens)
            adres = f"{kod} {miasto}, {ulica}" if ulica else f"{kod} {miasto}"

            # Adres 2 (opcjonalny)
            # Szukamy kolejnego kodu po pierwszym adresie
            kod2_idx = None
            for idx in range(kod_idx + 2 + len(ulica_tokens), len(tokens)):
                if re_kod.match(tokens[idx]):
                    kod2_idx = idx
                    break
            if kod2_idx is not None and kod2_idx + 1 < len(tokens):
                kod2 = tokens[kod2_idx]
                miasto2 = tokens[kod2_idx + 1]
                ulica2_tokens = []
                for t2 in tokens[kod2_idx + 2:]:
                    ulica2_tokens.append(t2)
                ulica2 = " ".join(ulica2_tokens)
                adres2 = f"{kod2} {miasto2}, {ulica2}" if ulica2 else f"{kod2} {miasto2}"
                if adres:
                    adres += " | " + adres2
                else:
                    adres = adres2

        # Daty aktywacji / dezaktywacji
        if daty_idx:
            data_akt = tokens[daty_idx[0]]
            if len(daty_idx) > 1:
                data_dezakt = tokens[daty_idx[1]]

        wpis = {
            "nazwa": nazwa.strip() if nazwa else "",
            "adres": adres.strip() if adres else "",
            "pesel": pesel,
            "data_akt": data_akt,
            "data_dezakt": data_dezakt,
        }

        if numer_norm not in historia:
            historia[numer_norm] = []
        if not historia[numer_norm] or historia[numer_norm][-1] != wpis:
            historia[numer_norm].append(wpis)
        mapping[numer_norm] = wpis

    if verbose:
        print(f"[orange_nazwiska] znaleziono {len(mapping)} wpisow.")
        if mapping:
            print("  Przykladowe:")
            for k, v in list(mapping.items())[:10]:
                print(f"    {k} -> {v['nazwa']} | {v['adres']} | PESEL:{v['pesel']} | OD:{v['data_akt']} | DO:{v['data_dezakt']}")
    return mapping, historia


# ══════════════════════════════════════════════════════════════════════
# BTS
# ══════════════════════════════════════════════════════════════════════

def parse_orange_bts(path: str, verbose: bool = False) -> dict:
    mapping = {}
    text = pdf_to_text(path)
    for line in text.split("\n"):
        line = line.strip()
        if not line or not re.search(r'\d', line):
            continue
        if any(line.startswith(p) for p in _ORANGE_SKIP):
            continue
        if "Orange Polska" in line or "Nasz znak" in line:
            continue
        tokens = line.split()
        if len(tokens) < 10:
            continue
        idx_bts = None
        for i, t in enumerate(tokens):
            if ':' in t and re.match(r'^[A-Z0-9]+:[A-Z]$', t):
                idx_bts = i
                break
        if idx_bts is None:
            continue
        bts_id = tokens[idx_bts]
        idx_deg = None
        for i, t in enumerate(tokens):
            if '°' in t:
                idx_deg = i
                break
        if idx_deg is None or idx_deg < 5:
            continue
        idx_woj = idx_deg - 3
        if idx_woj <= idx_bts + 1:
            continue
        woj = tokens[idx_woj]
        if not re.match(r'^[A-ZĄĆĘŁŃÓŚŹŻ]{5,}$', woj):
            idx_woj = idx_deg - 4
            if idx_woj <= idx_bts + 1:
                continue
            woj = tokens[idx_woj]
            if not re.match(r'^[A-ZĄĆĘŁŃÓŚŹŻ]{5,}$', woj):
                continue
        idx_data = idx_bts + 1
        if idx_data < len(tokens) and re.match(r'^\d{4}-\d{2}-\d{2}$', tokens[idx_data]):
            idx_start = idx_data + 1
            if idx_start < len(tokens) and re.match(r'^\d{4}-\d{2}-\d{2}$', tokens[idx_start]):
                idx_start += 1
        else:
            idx_start = idx_bts + 1
        if idx_start >= idx_woj:
            continue
        miejsc_ulica = tokens[idx_start:idx_woj]
        adres = ", ".join(miejsc_ulica + [woj])
        mapping[bts_id] = adres
    if verbose:
        print(f"[orange_bts] znaleziono {len(mapping)} wpisow.")
        if mapping:
            print("  Przykladowe:")
            for k, v in list(mapping.items())[:5]:
                print(f"    {k} -> {v}")
    return mapping
