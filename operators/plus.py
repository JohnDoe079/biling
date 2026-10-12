#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parsery dla operatora Plus (Polkomtel) — billing w formacie Excel (.xls/.xlsx).

Kanoniczna struktura kolumn (po normalizacji nazw):
    poczatek, koniec, parametr (= msisdn abonenta),
    a msisdn, b msisdn, a bts address, b bts address, ...
Dane zaczynaja sie od wiersza 5 (header=4).
"""
import glob
import os
import re

import pandas as pd

from common import klucz_numer, normalizuj_numer
from operators.base import parser_niedosteppny  # parse_nazwiska/parse_bts jako placeholder


# ─────────────────────────────────────────────────────────────────────
# AUTODETEKCJA PLIKOW W FOLDERZE ABONENTA
# ─────────────────────────────────────────────────────────────────────
# Realne nazwy z systemu Polkomtel:
#   ...-wyniki-8275782-dane_abonenckie-2026-05-25-18-19-30.774.xls
#   ...-wyniki-8275782-wykaz_polaczen-...xls
#   ...-wyniki-8275782-transmisja_danych-...xls
# Token "8275782" laczy pliki jednego numeru.

_RE_PLIK = re.compile(
    r"wyniki-(?P<token>\d+)-(?:(?:dane_)?)(?P<rola>wykaz_polaczen|dane_abonenckie|transmisja_danych)",
    re.IGNORECASE)

def autodetect(folder: str):
    """Zgodnie ze starym interfejsem: zwraca pojedynczy zestaw (pierwszy napotkany)."""
    ds = datasets(folder)
    if not ds:
        return {"wykaz": None, "nazwiska": None, "bts": None}
    d0 = ds[0]
    return {"wykaz": d0["wykaz"], "nazwiska": d0["nazwiska"], "bts": d0["bts"]}

def datasets(folder: str):
    """
    Zwraca liste zestawow danych: [{token, wykaz, nazwiska, transmisja, bts}].
    Jeden zestaw = jeden numer (token z nazwy pliku).
    """
    import glob
    pliki = sorted(glob.glob(os.path.join(folder, "*.xls*")) +
                   glob.glob(os.path.join(folder, "*.pdf")))
    grupy = {}
    inne = []
    for f in pliki:
        m = _RE_PLIK.search(os.path.basename(f))
        if m:
            g = grupy.setdefault(m.group("token"), {})
            g[m.group("rola")] = f
        else:
            inne.append(f)
    out = []
    for token in sorted(grupy):
        g = grupy[token]
        if "wykaz_polaczen" not in g and "transmisja_danych" not in g:
            continue
        out.append({
            "token": token,
            "wykaz": g.get("wykaz_polaczen"),
            "nazwiska": g.get("dane_abonenckie"),
            "transmisja": g.get("transmisja_danych"),
            "bts": None,
        })
    if not out and inne:
        inne.sort(key=lambda p: os.path.getsize(p), reverse=True)
        out.append({"token": None, "wykaz": inne[0], "nazwiska": None,
                    "transmisja": inne[1] if len(inne) > 1 else None, "bts": None})
    return out


# ─────────────────────────────────────────────────────────────────────
# WYKAZ POLACZEN
# ─────────────────────────────────────────────────────────────────────

def _czysc_wartosc(v):
    s = str(v).strip()
    if s in ("nan", "None", "-"):
        return ""
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s

def parse_plus(path: str, verbose: bool = False):
    """
    Zwraca (df, msisdn).
    Kolumny kanoniczne jak dla Orange. W billingu Plusa nie ma IMEI/IMSI —
    kolumny imei_a/imei_b/imsi_a/imsi_b sa puste (uzupełniane jesli kiedys
    pojawia sie w pliku).
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xls", ".xlsx"):
        engine = "xlrd" if ext == ".xls" else "openpyxl"
        raw = pd.read_excel(path, header=4, engine=engine)
    else:
        raise ValueError(f"Nieobsługiwany format pliku Plus: {ext}")

    df = raw.copy()
    df.columns = df.columns.str.strip().str.lower()

    # Mapowanie kolumn kanonicznych
    cols = {}
    for c in df.columns:
        cols[c] = c
    def pobierz(*nazwy):
        for n in nazwy:
            if n in df.columns:
                return df[n]
        return pd.Series([""] * len(df))

    poczatek = pobierz("początek", "poczatek", "start", "data początek")
    koniec   = pobierz("koniec", "end", "data koniec")

    poczatek = pd.to_datetime(poczatek, errors="coerce")
    koniec   = pd.to_datetime(koniec, errors="coerce")
    czas_trwania = (koniec - poczatek).dt.total_seconds()

    parametr = pobierz("parametr", "msisdn", "numer abonenta", "nr abonenta")
    a_msisdn = pobierz("a msisdn", "a_msisdn", "numer a", "strona a")
    b_msisdn = pobierz("b msisdn", "b_msisdn", "numer b", "strona b")
    a_bts    = pobierz("a bts address", "a bts", "bts a")
    b_bts    = pobierz("b bts address", "b bts", "bts b")
    imei_a   = pobierz("a imei", "imei a")
    imei_b   = pobierz("b imei", "imei b")
    imsi_a   = pobierz("a imsi", "imsi a")
    imsi_b   = pobierz("b imsi", "imsi b")

    # Typ zdarzenia — Plus nie zawsze ma te kolumne; domyslnie VOICE
    typ = pobierz("typ", "rodzaj", "typ zdarzenia", "usługa", "usluga")
    typ = typ.map(_czysc_wartosc).replace("", "VOICE").str.upper()

    out = pd.DataFrame({
        "data": poczatek.dt.strftime("%Y-%m-%d"),
        "czas": poczatek.dt.strftime("%H:%M:%S"),
        "czas_trwania": czas_trwania.where(czas_trwania.notna(), None),
        "typ": typ,
        "strona_a": a_msisdn.map(_czysc_wartosc),
        "bts_a": a_bts.map(_czysc_wartosc),
        "imei_a": imei_a.map(_czysc_wartosc),
        "imsi_a": imsi_a.map(_czysc_wartosc),
        "strona_b": b_msisdn.map(_czysc_wartosc),
        "bts_b": b_bts.map(_czysc_wartosc),
        "imei_b": imei_b.map(_czysc_wartosc),
        "imsi_b": imsi_b.map(_czysc_wartosc),
    })
    out = out[out["strona_a"].astype(str).str.strip() != ""]
    out = out.reset_index(drop=True)

    # MSISDN abonenta: najczestszy 'parametr', bo billing moze obejmowac wiele numerow
    msisdn = None
    param_s = parametr.map(_czysc_wartosc)
    param_s = param_s[param_s != ""]
    if not param_s.empty:
        msisdn = klucz_numer(param_s.value_counts().idxmax())

    if verbose:
        print(f"[plus] sparsowano {len(out)} rekordow, msisdn={msisdn}")

    return out, msisdn


# ─────────────────────────────────────────────────────────────────────
# NAZWISKA / BTS — do dopisania gdy dostarczysz wzorce
# ─────────────────────────────────────────────────────────────────────

parse_nazwiska = parser_niedosteppny("Plus (Polkomtel)")
parse_bts = parser_niedosteppny("Plus (Polkomtel)")
