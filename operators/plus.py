#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parsery dla operatora Plus (Polkomtel) — format Excel .xls/.xlsx z systemu QR.

Struktura kazdego pliku:
  - sekcja "Parametry zadania" (numer MSISDN = analizowany abonent),
  - sekcja "Opis kolumn" (zmienna dlugosc!),
  - wiersz naglowka zaczynajacy sie od "Parametr",
  - wiersze danych.

Rodzaje plikow (rozpoznawane po naglowku, nie po nazwie):
  wykaz_polaczen:  Usługa/Typ | A/B/C MSISDN | A/B/C IMEI | A/B/C IMSI |
                   Początek | Koniec | A/B/C BTS ADDRESS | ... | GCR
  dane_abonenckie: MSISDN | PESEL | SIM | ... | Ważne od/do | Imię i Nazwisko/Nazwa | Adres | Status
  transmisja:      MSISDN | IMEI | IMSI | IP | Początek | Koniec | Czas trwania | BTS ADDRESS | ...

Typy zdarzen Plusa -> kanoniczne:
  MOC/PTC/POC/MTC -> VOICE   (A = iniciujacy, B = odbierajacy;
                              dla analizowanego numeru kierunek wynika
                              automatycznie z tego, czy stoi w A czy w B)
  SMO/SMT -> SMS, MMR -> MMS, UCAT/UCAM -> PRÓBA, FORW -> FWD
"""
import glob
import os
import re

import pandas as pd

from common import klucz_numer
from operators.base import parser_niedosteppny


# ─────────────────────────────────────────────────────────────────────
# NISKOPOZIOMOWE WCZYTYWANIE
# ─────────────────────────────────────────────────────────────────────

_RE_NUMER_ZADANIA = re.compile(r"(\d{9,15})")
_RE_NAGLOWEK = re.compile(r"^parametr$", re.IGNORECASE)

def _wczytaj_arkusz(path: str):
    """Zwraca (ramka danych z wlasciwym naglowkiem, numer_msisdn_zadania)."""
    ext = os.path.splitext(path)[1].lower()
    engine = "xlrd" if ext == ".xls" else "openpyxl"
    raw = pd.read_excel(path, header=None, engine=engine)
    raw = raw.dropna(how="all")

    msisdn = None
    # szukaj numeru zadania w pierwszych wierszach (sekcja Parametry zadania)
    for i in range(min(10, len(raw))):
        for v in raw.iloc[i].astype(str):
            m = _RE_NUMER_ZADANIA.search(v.replace(".0", ""))
            if m:
                msisdn = m.group(1)
                break
        if msisdn:
            break

    # szukaj wiersza naglowka (pierwsza komorka == "Parametr")
    idx_header = None
    for i in range(len(raw)):
        if _RE_NAGLOWEK.match(str(raw.iloc[i, 0]).strip()):
            idx_header = i
            break
    if idx_header is None:
        return pd.DataFrame(), msisdn

    header = [str(h).strip() for h in raw.iloc[idx_header]]
    df = raw.iloc[idx_header + 1:].copy()
    df.columns = header
    df = df.dropna(how="all").reset_index(drop=True)
    return df, msisdn


def _czysto(v):
    s = str(v).strip()
    if s in ("nan", "None", "NaT", "-", "nat"):
        return ""
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    return s


_MAPA_TYPOW = {
    "MOC": "VOICE", "PTC": "VOICE", "POC": "VOICE", "MTC": "VOICE",
    "SMO": "SMS", "SMT": "SMS",
    "MMR": "MMS",
    "UCAT": "PRÓBA", "UCAM": "PRÓBA",
    "FORW": "FWD",
}


# ─────────────────────────────────────────────────────────────────────
# WYKAZ POLACZEN / TRANSMISJA
# ─────────────────────────────────────────────────────────────────────

def parse_plus(path: str, verbose: bool = False):
    """
    Zwraca (df, msisdn). Obsluguje zarowno wykaz_polaczen jak i transmisja_danych.
    """
    df, msisdn = _wczytaj_arkusz(path)
    if df.empty:
        if verbose:
            print(f"[plus] pusty plik lub brak danych: {os.path.basename(path)}")
        return pd.DataFrame(columns=[
            "data", "czas", "czas_trwania", "typ", "strona_a", "bts_a", "imei_a",
            "imsi_a", "strona_b", "bts_b", "imei_b", "imsi_b"]), msisdn

    cols = {c.lower(): c for c in df.columns}

    def kol(*nazwy):
        for n in nazwy:
            if n in cols:
                return df[cols[n]]
        return pd.Series([""] * len(df))

    # --- wspolne: czas ---
    poczatek = pd.to_datetime(kol("początek", "poczatek"), errors="coerce")
    koniec   = pd.to_datetime(kol("koniec"), errors="coerce")
    czas_trwania_kol = kol("czas trwania")
    if czas_trwania_kol.astype(str).str.strip().ne("").any():
        czas_trwania = pd.to_numeric(czas_trwania_kol.map(_czysto).replace("", None), errors="coerce")
    else:
        czas_trwania = (koniec - poczatek).dt.total_seconds()

    if "usługa/typ" in cols or "usługa" in cols or "typ" in cols:
        # --- wykaz polaczen ---
        typ = kol("usługa/typ", "usługa", "typ").map(_czysto).str.upper()
        typ = typ.map(lambda t: _MAPA_TYPOW.get(t, t or "VOICE"))
        out = pd.DataFrame({
            "data": poczatek.dt.strftime("%Y-%m-%d"),
            "czas": poczatek.dt.strftime("%H:%M:%S"),
            "czas_trwania": czas_trwania,
            "typ": typ,
            "strona_a": kol("a msisdn").map(_czysto),
            "bts_a": kol("a bts address").map(_czysto),
            "imei_a": kol("a imei/a esn", "a imei").map(_czysto),
            "imsi_a": kol("a imsi").map(_czysto),
            "strona_b": kol("b msisdn").map(_czysto),
            "bts_b": kol("b bts address").map(_czysto),
            "imei_b": kol("b imei/b esn", "b imei").map(_czysto),
            "imsi_b": kol("b imsi").map(_czysto),
        })
    else:
        # --- transmisja danych ---
        out = pd.DataFrame({
            "data": poczatek.dt.strftime("%Y-%m-%d"),
            "czas": poczatek.dt.strftime("%H:%M:%S"),
            "czas_trwania": czas_trwania,
            "typ": "DATA",
            "strona_a": kol("msisdn").map(_czysto),
            "bts_a": kol("bts address").map(_czysto),
            "imei_a": kol("imei").map(_czysto),
            "imsi_a": kol("imsi").map(_czysto),
            "strona_b": "",
            "bts_b": "",
            "imei_b": "",
            "imsi_b": "",
        })

    out = out[out["strona_a"].astype(str).str.strip() != ""]
    out = out[out["data"].notna() & (out["data"] != "NaT")]
    out = out.reset_index(drop=True)

    if verbose:
        print(f"[plus] {os.path.basename(path)}: {len(out)} rekordow, msisdn={msisdn}")
    return out, msisdn


# ─────────────────────────────────────────────────────────────────────
# DANE ABENENCKIE  ->  mapping nazwisk + historia zmian
# ─────────────────────────────────────────────────────────────────────

_TEKST_BRAK_ABONENTA = "nie obsługiwany przez polkomtel"

def parse_plus_nazwiska(path: str, verbose: bool = False):
    """Zwraca (mapping, historia) jak parser Orange."""
    df, _ = _wczytaj_arkusz(path)
    mapping, historia = {}, {}
    if df.empty:
        return mapping, historia
    cols = {c.lower(): c for c in df.columns}

    def kol(*nazwy):
        for n in nazwy:
            if n in cols:
                return df[cols[n]]
        return pd.Series([""] * len(df))

    msisdn_s   = kol("msisdn").map(_czysto)
    pesel_s    = kol("pesel").map(_czysto)
    nip_s      = kol("nip").map(_czysto)
    sim_s      = kol("sim").map(_czysto)
    typms_s    = kol("typ msisdn").map(_czysto)
    status_s   = kol("status").map(_czysto)
    nazwa_s    = kol("imię i nazwisko/nazwa", "imię i nazwisko", "nazwa").map(_czysto)
    adres_s    = kol("adres").map(_czysto)
    wazne_od   = kol("ważne od", "wazne od").map(_czysto)
    wazne_do   = kol("ważne do", "wazne do").map(_czysto)

    for i in range(len(df)):
        num = klucz_numer(msisdn_s.iloc[i])
        if not num:
            continue
        nazwa = nazwa_s.iloc[i]
        if _TEKST_BRAK_ABONENTA.lower() in nazwa.lower():
            nazwa = ""  # numer nieobslugiwany w tym okresie
        wpis = {
            "nazwa": nazwa,
            "adres": adres_s.iloc[i],
            "pesel": pesel_s.iloc[i],
            "nip": nip_s.iloc[i],
            "sim": sim_s.iloc[i],
            "typ_msisdn": typms_s.iloc[i],
            "status": status_s.iloc[i],
            "data_akt": (wazne_od.iloc[i] or "")[:10],
            "data_dezakt": (wazne_do.iloc[i] or "")[:10],
        }
        historia.setdefault(num, [])
        if not historia[num] or historia[num][-1] != wpis:
            historia[num].append(wpis)
        if nazwa or pesel_s.iloc[i] or adres_s.iloc[i]:
            mapping[num] = wpis

    if verbose:
        print(f"[plus_nazwiska] {os.path.basename(path)}: {len(mapping)} wpisow")
    return mapping, historia


# ─────────────────────────────────────────────────────────────────────
# AUTODETEKCJA PLIKOW / ZESTAWY
# ─────────────────────────────────────────────────────────────────────
# Realne nazwy z systemu Polkomtel:
#   ...-wyniki-8275782-dane_abonenckie-2026-05-25-18-19-30.774.xls
#   ...-wyniki-8275782-wykaz_polaczen-...xls
#   ...-wyniki-8275782-transmisja_danych-...xls
# Token (np. 8275782) to ID zapytania — laczy pliki jednego numeru.

_RE_PLIK = re.compile(
    r"wyniki-(?P<token>\d+)-(?:(?:dane_)?)(?P<rola>wykaz_polaczen|dane_abonenckie|transmisja_danych)",
    re.IGNORECASE)

def autodetect(folder: str):
    ds = datasets(folder)
    if not ds:
        return {"wykaz": None, "nazwiska": None, "bts": None}
    d0 = ds[0]
    return {"wykaz": d0["wykaz"], "nazwiska": d0["nazwiska"], "bts": d0["bts"]}

def datasets(folder: str):
    """Zwraca liste zestawow: [{token, wykaz, nazwiska, transmisja, bts}]."""
    pliki = sorted(glob.glob(os.path.join(folder, "*.xls*")) +
                   glob.glob(os.path.join(folder, "*.pdf")))
    grupy, inne = {}, []
    for f in pliki:
        m = _RE_PLIK.search(os.path.basename(f))
        if m:
            grupy.setdefault(m.group("token"), {})[m.group("rola")] = f
        else:
            inne.append(f)
    out = []
    for token in sorted(grupy):
        g = grupy[token]
        if "wykaz_polaczen" not in g and "transmisja_danych" not in g \
                and "dane_abonenckie" not in g:
            continue
        out.append({
            "token": token,
            "wykaz": g.get("wykaz_polaczen"),
            "nazwiska": g.get("dane_abonenckie"),
            "transmisja": g.get("transmisja_danych"),
            "bts": None,  # Plus podaje adres BTS wprost w rekordach
        })
    if not out and inne:
        inne.sort(key=lambda p: os.path.getsize(p), reverse=True)
        out.append({"token": None, "wykaz": inne[0], "nazwiska": None,
                    "transmisja": inne[1] if len(inne) > 1 else None, "bts": None})
    return out


parse_bts = parser_niedosteppny("Plus (Polkomtel)")  # BTS = adres wprost w rekordach
