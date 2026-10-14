#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analiza bilingow — orchestrator: raporty per numer (+ raport urzadzenia dla
danych kluczowanych po IMEI) oraz automatyczna analiza krzyzowa, gdy
analizowanych numerow MSISDN jest wiecej niz jeden.

Przebieg (bez zadnych pytan — wszystko wyprowadzone z folderu danych):
  1. Skanuje <dane>/<operator>/<abonent>/ (domyslnie ./input).
  2. Dla KAZDEGO zestawu generuje raport per numer (TXT+CSV) — rowniez gdy
     dane sa puste (raport z sekcjami "brak danych": numer nie wystepuje
     u danego operatora / pusty wykaz) albo gdy parser operatora nie jest
     jeszcze dostepny (raport-zalacznik z informacja o braku parsera).
  3. Zestawy kluczowane po IMEI (operator dostarczyl dane URZADZENIA zamiast
     numeru MSISDN) generuja raport urzadzenia: jakie numery MSISDN byly
     uzytkowane w tym telefonie, kiedy, z jakimi kontaktami i BTS.
  4. Gdy analizowanych jest >1 numer MSISDN, automatycznie powstaje DRUGI
     raport: analiza krzyzowa (RAPORT_ZBIORCZY_KRZYZOWY.txt/.csv).

Operator jest ZAWSZE brany z nazwy folderu (poziom 1), pliki z folderu
abonenta sa wykrywane automatycznie przez modul operators/<operator>.py.
Brak jakichkolwiek pytan interaktywnych.

Uzycie:
  python3 analizaBilling.py                      # ./input -> ./raport_bilingow (tylko CSV)
  python3 analizaBilling.py --dane ./input --outdir ./raporty
  python3 analizaBilling.py --numer 123456789    # tylko jeden numer / IMEI
  python3 analizaBilling.py --bez-krzyzowej      # wylacz analize krzyzowa
  python3 analizaBilling.py --txt                # raporty dodatkowo w TXT

Wymagania systemowe (Debian/Ubuntu):
  sudo apt install poppler-utils python3-pandas
  pip install xlrd openpyxl   # dla bilingow Plus (.xls/.xlsx)
"""
import argparse
import csv
import os
import re
import sys
from datetime import datetime, timedelta

import pandas as pd

from common import (
    skanuj_dane, klucz_numer, normalizuj_numer, format_numer, fmt_czas,
    okres_bilingow, dane_abonenta, BLANK, NIE_BTS, NIE_IMEI, _clean_counts,
)
from operators import orange, tmobile, plus, play
from operators.base import BrakParsaraError


# ══════════════════════════════════════════════════════════════════════
# REJESTR OPERATOROW
# ══════════════════════════════════════════════════════════════════════
# Operator NIGDY nie jest wybierany z menu — jest brany z nazwy folderu.
# "parse" == None oznacza, ze parser operatora nie jest jeszcze gotowy
# (raport-zalacznik z informacja, analiza nie przerywa sie).

OPERATORZY = {
    "orange": {
        "nazwa": "Orange Polska",
        "modul": orange,
        "parse": orange.parse_orange,
        "parse_nazwiska": orange.parse_orange_nazwiska,
        "parse_bts": orange.parse_orange_bts,
    },
    "tmobile": {
        "nazwa": "T-Mobile Polska",
        "modul": tmobile,
        "parse": None, "parse_nazwiska": None, "parse_bts": None,
    },
    "plus": {
        "nazwa": "Plus (Polkomtel)",
        "modul": plus,
        "parse": plus.parse_plus,
        "parse_nazwiska": plus.parse_plus_nazwiska,
        "parse_bts": None,   # Plus podaje adres BTS wprost w rekordach
    },
    "play": {
        "nazwa": "Play (P4)",
        "modul": play,
        "parse": None, "parse_nazwiska": None, "parse_bts": None,
    },
}

KOLUMNY_KANONICZNE = [
    "data", "czas", "czas_trwania", "typ", "strona_a", "bts_a", "imei_a",
    "imsi_a", "strona_b", "bts_b", "imei_b", "imsi_b",
]

_RE_MSISDN = re.compile(r"^\d{9,12}$")
_RE_IMEI = re.compile(r"^\d{14,16}$")


# ══════════════════════════════════════════════════════════════════════
# ANALIZA (per numer)
# ══════════════════════════════════════════════════════════════════════

def _k(s):
    """Kanoniczne klucze numerow (48xxx -> xxx) do porownan i grupowan."""
    return s.map(klucz_numer)

def kontakty_zdarzenia(df, target, nazwiska_map=None):
    d = df.copy()
    d["_ka"] = _k(d["strona_a"])
    d["_kb"] = _k(d["strona_b"])
    voice = d[d["typ"] == "VOICE"]
    proba = d[d["typ"] == "PRÓBA"]
    wych = voice[voice["_ka"] == target].groupby("_kb").agg(
        voice_wychodzace=("_kb", "size"),
        czas_wychodzacy_s=("czas_trwania", "sum"))
    przych = voice[voice["_kb"] == target].groupby("_ka").agg(
        voice_przychodzace=("_ka", "size"),
        czas_przychodzacy_s=("czas_trwania", "sum"))
    proba_wych = proba[proba["_ka"] == target].groupby("_kb").size()
    proba_wych.name = "proba_wych"
    proba_przych = proba[proba["_kb"] == target].groupby("_ka").size()
    proba_przych.name = "proba_przych"
    proba_df = pd.concat([proba_wych, proba_przych], axis=1).fillna(0).astype(int)
    proba_df["proba_razem"] = proba_df["proba_wych"] + proba_df["proba_przych"]
    sub = pd.concat([voice, proba])
    a_rows = sub[sub["_ka"] == target][["_kb", "data"]].rename(columns={"_kb": "numer"})
    b_rows = sub[sub["_kb"] == target][["_ka", "data"]].rename(columns={"_ka": "numer"})
    all_rows = pd.concat([a_rows, b_rows])
    if not all_rows.empty:
        zakres = all_rows.groupby("numer")["data"].agg(["min", "max"])
        zakres["zakres_czasu"] = zakres["min"] + " - " + zakres["max"]
    else:
        zakres = pd.DataFrame(columns=["min", "max", "zakres_czasu"])
    out = wych.join(przych, how="outer").fillna(0).infer_objects(copy=False)
    out = out.join(proba_df[["proba_razem"]], how="outer").fillna(0).infer_objects(copy=False)
    out = out.join(zakres[["zakres_czasu"]], how="outer").fillna("")
    for col in ["voice_wychodzace", "voice_przychodzace", "czas_wychodzacy_s", "czas_przychodzacy_s", "proba_razem"]:
        out[col] = out[col].astype(int)
    out["razem"] = out["voice_wychodzace"] + out["voice_przychodzace"] + out["proba_razem"]
    out.index.name = "numer_kontaktu"
    out = out.sort_values("razem", ascending=False).reset_index()
    if nazwiska_map:
        out["nazwa_kontaktu"] = out["numer_kontaktu"].astype(str).map(
            lambda x: nazwiska_map.get(normalizuj_numer(x), {}).get("nazwa", "")
        )
    return out

def kontakty_sms(df, target, nazwiska_map=None):
    d = df.copy()
    d["_ka"] = _k(d["strona_a"])
    d["_kb"] = _k(d["strona_b"])
    msg = d[d["typ"].isin(["SMS", "MMS"])]
    wych = msg[msg["_ka"] == target].groupby("_kb").size()
    wych.name = "sms_wychodzace"
    przych = msg[msg["_kb"] == target].groupby("_ka").size()
    przych.name = "sms_przychodzace"
    out = pd.concat([wych, przych], axis=1).fillna(0).infer_objects(copy=False).astype(int)
    out["sms_razem"] = out["sms_wychodzace"] + out["sms_przychodzace"]
    a_rows = msg[msg["_ka"] == target][["_kb", "data"]].rename(columns={"_kb": "numer"})
    b_rows = msg[msg["_kb"] == target][["_ka", "data"]].rename(columns={"_ka": "numer"})
    all_rows = pd.concat([a_rows, b_rows])
    if not all_rows.empty:
        zakres = all_rows.groupby("numer")["data"].agg(["min", "max"])
        zakres["zakres_czasu"] = zakres["min"] + " - " + zakres["max"]
        out = out.join(zakres[["zakres_czasu"]], how="outer").fillna("")
    else:
        out["zakres_czasu"] = ""
    out.index.name = "numer_kontaktu"
    out = out.sort_values("sms_razem", ascending=False).reset_index()
    if nazwiska_map:
        out["nazwa_kontaktu"] = out["numer_kontaktu"].astype(str).map(
            lambda x: nazwiska_map.get(normalizuj_numer(x), {}).get("nazwa", "")
        )
    return out

def bts_polaczone(df, target, bts_map=None):
    sub_a = df[_k(df["strona_a"]) == target]
    sub_b = df[_k(df["strona_b"]) == target]
    counts_a = _clean_counts(sub_a["bts_a"], wyklucz=NIE_BTS)
    counts_b = _clean_counts(sub_b["bts_b"], wyklucz=NIE_BTS)
    out_a = counts_a.rename_axis("bts").reset_index(name="inicjujace")
    out_b = counts_b.rename_axis("bts").reset_index(name="odbierajace")
    out = out_a.merge(out_b, on="bts", how="outer").fillna(0)
    out["inicjujace"] = out["inicjujace"].astype(int)
    out["odbierajace"] = out["odbierajace"].astype(int)
    if bts_map:
        out["adres_bts"] = out["bts"].astype(str).map(lambda x: bts_map.get(x, ""))
    out = out.sort_values("inicjujace", ascending=False).reset_index(drop=True)
    return out

def imei_dla_numeru(df, target):
    sub = df[(_k(df["strona_a"]) == target) | (_k(df["strona_b"]) == target)]
    imei_a = sub[_k(sub["strona_a"]) == target]["imei_a"]
    imei_b = sub[_k(sub["strona_b"]) == target]["imei_b"]
    all_imei = pd.concat([imei_a, imei_b])
    all_imei = all_imei[~all_imei.isin(NIE_IMEI) & all_imei.notna()]
    return all_imei.value_counts().rename_axis("imei").reset_index(name="liczba_zdarzen")

def internet_stats(df, target):
    data = df[df["typ"] == "DATA"]
    wych = data[_k(data["strona_a"]) == target]
    przych = data[_k(data["strona_b"]) == target]
    razem = len(wych) + len(przych)
    czas_s = 0
    if not wych.empty:
        czas_s += wych["czas_trwania"].sum()
    if not przych.empty:
        czas_s += przych["czas_trwania"].sum()
    all_data = pd.concat([wych, przych])
    if not all_data.empty:
        zakres = all_data["data"].min() + " - " + all_data["data"].max()
    else:
        zakres = ""
    return {"razem": int(razem), "czas_s": int(czas_s), "zakres_czasu": zakres}


def stats_dla_okresu(df, target, data_od, data_do):
    """Zwraca statystyki aktywnosci numeru target w danym okresie."""
    mask = pd.Series(True, index=df.index)
    if data_od:
        mask &= df["data"] >= data_od
    if data_do:
        mask &= df["data"] <= data_do
    sub = df[mask]

    voice = sub[sub["typ"] == "VOICE"]
    proba = sub[sub["typ"] == "PRÓBA"]
    sms = sub[sub["typ"].isin(["SMS", "MMS"])]

    v_wych = len(voice[voice["strona_a"] == target])
    v_przych = len(voice[voice["strona_b"] == target])
    p_wych = len(proba[proba["strona_a"] == target])
    p_przych = len(proba[proba["strona_b"] == target])
    czas_wych = voice[voice["strona_a"] == target]["czas_trwania"].sum()
    czas_przych = voice[voice["strona_b"] == target]["czas_trwania"].sum()

    s_wych = len(sms[sms["strona_a"] == target])
    s_przych = len(sms[sms["strona_b"] == target])

    return {
        "voice_wych": int(v_wych),
        "voice_przych": int(v_przych),
        "proba_wych": int(p_wych),
        "proba_przych": int(p_przych),
        "sms_wych": int(s_wych),
        "sms_przych": int(s_przych),
        "czas_wych_s": int(czas_wych) if not pd.isna(czas_wych) else 0,
        "czas_przych_s": int(czas_przych) if not pd.isna(czas_przych) else 0,
    }


# ══════════════════════════════════════════════════════════════════════
# RAPORTY PER NUMER (TXT + CSV)
# ══════════════════════════════════════════════════════════════════════

def generuj_raport_txt(target, kp, ks, bts, imei_df, abonent, inet, okres_od, okres_do,
                       historia_abonentow=None, historia_kontaktow=None, bloki=None,
                       uwagi=None):
    if bloki is None:
        bloki = [{
            'naglowek': None,
            'kp': kp, 'ks': ks, 'bts': bts, 'imei': imei_df, 'inet': inet,
            'abonent': abonent, 'od': okres_od, 'do': okres_do,
            'historia_kontaktow': historia_kontaktow
        }]

    lines = []
    lines.append("=" * 120)
    lines.append("  RAPORT KONCOWY — ANALIZA BILINGOW")
    main_abonent = abonent if (abonent and abonent.get("nazwa")) else bloki[-1]['abonent']
    meta = f"  Numer: {format_numer(target)}"
    if main_abonent.get("nazwa"):
        meta += f" | Abonent: {main_abonent['nazwa']}"
    if main_abonent.get("adres"):
        meta += f" | Adres: {main_abonent['adres']}"
    if main_abonent.get("pesel"):
        meta += f" | PESEL/REGON: {main_abonent['pesel']}"
    if main_abonent.get("sim"):
        meta += f" | SIM: {main_abonent['sim']}"
    if main_abonent.get("typ_msisdn"):
        meta += f" | Forma: {main_abonent['typ_msisdn']}"
    if main_abonent.get("status"):
        meta += f" | Status: {main_abonent['status']}"
    lines.append(meta)
    lines.append(f"  Okres bilingow: {okres_od} - {okres_do}")
    if uwagi:
        lines.append(f"  UWAGI: {uwagi}")
    lines.append("=" * 120)
    lines.append("")

    # HISTORIA ZMIAN ABONENTA — globalnie
    if historia_abonentow and target in historia_abonentow and len(historia_abonentow[target]) > 1:
        lines.append("-" * 120)
        lines.append("  HISTORIA ZMIAN ABONENTA")
        lines.append("-" * 120)
        lines.append("  {:>4} {:<12} {:<12} {:<36} {:<16} {:<36}".format(
            "Lp", "Data od", "Data do", "Nazwa / Firma", "PESEL/REGON", "Adres"))
        lines.append("-" * 120)
        for idx, wpis in enumerate(historia_abonentow[target], 1):
            lines.append("  {:>4} {:<12} {:<12} {:<36} {:<16} {:<36}".format(
                idx,
                (wpis.get('data_akt', '') or "-")[:12],
                (wpis.get('data_dezakt', '') or "-")[:12],
                (wpis['nazwa'] or "(brak danych)")[:36],
                (wpis['pesel'] or "-")[:16],
                (wpis['adres'] or "(brak danych)")[:36]))
        lines.append("")

    for bi, blok in enumerate(bloki, 1):
        if blok.get('naglowek'):
            lines.append("=" * 120)
            lines.append(f"  {blok['naglowek']}")
            lines.append("=" * 120)
            lines.append("")
        elif len(bloki) > 1:
            lines.append("-" * 120)
            lines.append(f"  OKRES {bi}: {blok['od']} – {blok['do']}")
            lines.append("-" * 120)
            lines.append("")

        hk = blok.get('historia_kontaktow')
        if hk:
            lines.append("-" * 120)
            lines.append("  HISTORIA ZMIAN ABONENTOW KONTAKTOW")
            lines.append("-" * 120)
            lines.append("  {:>4} {:<16} {:<12} {:<12} {:<36} {:<16} {:<36}".format(
                "Lp", "Numer", "Data od", "Data do", "Nazwa / Firma", "PESEL/REGON", "Adres"))
            lines.append("-" * 120)
            global_idx = 1
            for numer, wpisy in sorted(hk.items()):
                for wpis in wpisy:
                    lines.append("  {:>4} {:<16} {:<12} {:<12} {:<36} {:<16} {:<36}".format(
                        global_idx, format_numer(numer)[:16],
                        (wpis.get('data_akt', '') or "-")[:12],
                        (wpis.get('data_dezakt', '') or "-")[:12],
                        (wpis['nazwa'] or "(brak danych)")[:36],
                        (wpis['pesel'] or "-")[:16],
                        (wpis['adres'] or "(brak danych)")[:36]))
                    global_idx += 1
            lines.append("")

        # SEKCJA 1
        kp_b = blok['kp']
        lines.append("-" * 120)
        lines.append("  SEKCJA 1: KONTAKTY GLOSOWE + PROBY (bez FWD, DATA, SMS, MMS)")
        lines.append("-" * 120)
        if not kp_b.empty:
            lines.append("  {:>4} {:<16} {:<32} {:>8} {:>8} {:>8} {:>8} {:>18} {:>18} {:>22}".format(
                "Lp", "Numer telefonu", "Imie i nazwisko / Firma",
                "Wych", "Przych", "Proba", "Razem",
                "Czas wych", "Czas przych", "Zakres czasu"))
            lines.append("-" * 120)
            for i, (_, r) in enumerate(kp_b.iterrows(), 1):
                nazwa = r.get('nazwa_kontaktu', '')
                if not nazwa:
                    nazwa = "(brak danych)"
                line = "  {:>4} {:<16} {:<32} {:>8} {:>8} {:>8} {:>8} {:>18} {:>18} {:>22}".format(
                    i, format_numer(r['numer_kontaktu']), nazwa[:32],
                    r['voice_wychodzace'], r['voice_przychodzace'], r['proba_razem'], r['razem'],
                    fmt_czas(r['czas_wychodzacy_s']), fmt_czas(r['czas_przychodzacy_s']),
                    r.get('zakres_czasu', ''))
                lines.append(line)
        else:
            lines.append("  Brak zdarzen w tym okresie.")
        lines.append("")

        # SEKCJA 2
        ks_b = blok['ks']
        lines.append("-" * 100)
        lines.append("  SEKCJA 2: KONTAKTY SMS/MMS")
        lines.append("-" * 100)
        if not ks_b.empty:
            lines.append("  {:>4} {:<16} {:<32} {:>6} {:>6} {:>6} {:>22}".format(
                "Lp", "Numer telefonu", "Imie i nazwisko / Firma",
                "Wych", "Przych", "Razem", "Zakres czasu"))
            lines.append("-" * 100)
            for i, (_, r) in enumerate(ks_b.iterrows(), 1):
                nazwa = r.get('nazwa_kontaktu', '')
                if not nazwa:
                    nazwa = "(brak danych)"
                line = "  {:>4} {:<16} {:<32} {:>6} {:>6} {:>6} {:>22}".format(
                    i, format_numer(r['numer_kontaktu']), nazwa[:32],
                    r['sms_wychodzace'], r['sms_przychodzace'], r['sms_razem'],
                    r.get('zakres_czasu', ''))
                lines.append(line)
        else:
            lines.append("  Brak zdarzen w tym okresie.")
        lines.append("")

        # SEKCJA 3
        inet_b = blok['inet']
        lines.append("-" * 80)
        lines.append("  SEKCJA 3: INTERNET (DATA)")
        lines.append("-" * 80)
        if inet_b['razem'] > 0:
            lines.append("  {:<24} {:>12} {:>24}".format("Opis", "Ilosc sesji", "Suma czasu"))
            lines.append("-" * 80)
            lines.append("  {:<24} {:>12} {:>24}".format(
                "Internet (DATA)", inet_b["razem"], fmt_czas(inet_b["czas_s"])))
            if inet_b["zakres_czasu"]:
                lines.append("  {:<24} {:>12} {:>24}".format("", "", inet_b["zakres_czasu"]))
        else:
            lines.append("  Brak zdarzen w tym okresie.")
        lines.append("")

        # SEKCJA 4
        bts_b = blok['bts']
        lines.append("-" * 100)
        lines.append("  SEKCJA 4: STACJE BTS")
        lines.append("-" * 100)
        if not bts_b.empty:
            lines.append("  {:>4} {:<20} {:>10} {:>10} {:<50}".format(
                "Lp", "Kod BTS", "Inicjujace", "Odbierajace", "Adres stacji"))
            lines.append("-" * 100)
            for i, (_, r) in enumerate(bts_b.iterrows(), 1):
                adres = r.get('adres_bts', '') or "(brak danych)"
                line = "  {:>4} {:<20} {:>10} {:>10} {:<50}".format(
                    i, r['bts'], r['inicjujace'], r['odbierajace'], adres)
                lines.append(line)
        else:
            lines.append("  Brak zdarzen w tym okresie.")
        lines.append("")

        # SEKCJA 5
        imei_b = blok['imei']
        if not imei_b.empty:
            lines.append("-" * 100)
            lines.append("  SEKCJA 5: URZADZENIA (IMEI) UZYWANE PRZEZ ANALIZOWANY NUMER")
            lines.append("-" * 100)
            lines.append("  {:>4} {:<18} {:>16} {:<30}".format("Lp", "IMEI", "Liczba zdarzen", "Uwagi"))
            lines.append("-" * 100)
            for i, (_, r) in enumerate(imei_b.iterrows(), 1):
                uwagi_r = "(glowne)" if i == 1 else ""
                line = "  {:>4} {:<18} {:>16} {:<30}".format(i, r['imei'], r['liczba_zdarzen'], uwagi_r)
                lines.append(line)
            if len(imei_b) > 1:
                lines.append("")
                lines.append(f"  UWAGA: Wykryto {len(imei_b)} roznych urzadzen (IMEI) dla numeru {format_numer(target)}.")
            lines.append("")
        else:
            lines.append("-" * 100)
            lines.append("  SEKCJA 5: URZADZENIA (IMEI)")
            lines.append("-" * 100)
            lines.append("  Brak zdarzen w tym okresie.")
            lines.append("")

    lines.append("=" * 120)
    lines.append("  KONIEC RAPORTU")
    lines.append("=" * 120)
    return "\n".join(lines)


def generuj_raport_csv(target, kp, ks, bts, imei_df, abonent, inet, okres_od, okres_do, outpath,
                       historia_abonentow=None, historia_kontaktow=None, bloki=None,
                       uwagi=None):
    if bloki is None:
        bloki = [{
            'naglowek': None,
            'kp': kp, 'ks': ks, 'bts': bts, 'imei': imei_df, 'inet': inet,
            'abonent': abonent, 'od': okres_od, 'do': okres_do,
            'historia_kontaktow': historia_kontaktow
        }]

    with open(outpath, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, delimiter=';', quoting=csv.QUOTE_MINIMAL)

        main_abonent = abonent if (abonent and abonent.get("nazwa")) else bloki[-1]['abonent']
        meta = f"RAPORT KONCOWY — ANALIZA BILINGOW | Numer: {format_numer(target)}"
        if main_abonent.get("nazwa"):
            meta += f" | Abonent: {main_abonent['nazwa']}"
        if main_abonent.get("adres"):
            meta += f" | Adres: {main_abonent['adres']}"
        if main_abonent.get("pesel"):
            meta += f" | PESEL/REGON: {main_abonent['pesel']}"
        if main_abonent.get("sim"):
            meta += f" | SIM: {main_abonent['sim']}"
        if main_abonent.get("typ_msisdn"):
            meta += f" | Forma: {main_abonent['typ_msisdn']}"
        if main_abonent.get("status"):
            meta += f" | Status: {main_abonent['status']}"
        writer.writerow([meta])
        writer.writerow([f"Okres bilingow: {okres_od} - {okres_do}"])
        if uwagi:
            writer.writerow([f"UWAGI: {uwagi}"])
        writer.writerow([])

        # HISTORIA ZMIAN ABONENTA
        if historia_abonentow and target in historia_abonentow and len(historia_abonentow[target]) > 1:
            writer.writerow(["HISTORIA ZMIAN ABONENTA"])
            writer.writerow(["Lp", "Data od", "Data do", "Nazwa / Firma", "PESEL/REGON", "Adres"])
            for idx, wpis in enumerate(historia_abonentow[target], 1):
                writer.writerow([idx,
                                 wpis.get('data_akt', '') or '-',
                                 wpis.get('data_dezakt', '') or '-',
                                 wpis['nazwa'] or '(brak danych)',
                                 wpis['pesel'] or '-',
                                 wpis['adres'] or '(brak danych)'])
            writer.writerow([])

        for bi, blok in enumerate(bloki, 1):
            if blok.get('naglowek'):
                writer.writerow([blok['naglowek']])
                writer.writerow([])
            elif len(bloki) > 1:
                writer.writerow([f"OKRES {bi}: {blok['od']} – {blok['do']}"])
                writer.writerow([])

            hk = blok.get('historia_kontaktow')
            if hk:
                writer.writerow(["HISTORIA ZMIAN ABONENTOW KONTAKTOW"])
                writer.writerow(["Lp", "Numer", "Data od", "Data do", "Nazwa / Firma", "PESEL/REGON", "Adres"])
                global_idx = 1
                for numer, wpisy in sorted(hk.items()):
                    for wpis in wpisy:
                        writer.writerow([global_idx, format_numer(numer),
                                         wpis.get('data_akt', '') or '-',
                                         wpis.get('data_dezakt', '') or '-',
                                         wpis['nazwa'] or '(brak danych)',
                                         wpis['pesel'] or '-',
                                         wpis['adres'] or '(brak danych)'])
                        global_idx += 1
                writer.writerow([])

            # SEKCJA 1
            kp_b = blok['kp']
            writer.writerow(["SEKCJA 1: KONTAKTY GŁOSOWE + PRÓBY"])
            writer.writerow(["Lp", "Numer telefonu", "Imię i nazwisko / Firma",
                             "Połączenie wychodzące", "Połączenie przychodzące", "Próba połączenia", "Razem",
                             "Czas wychodzący", "Czas przychodzący", "Zakres czasu"])
            if not kp_b.empty:
                for i, (_, r) in enumerate(kp_b.iterrows(), 1):
                    writer.writerow([
                        i, format_numer(r['numer_kontaktu']), (r.get('nazwa_kontaktu', '') or '(brak danych)'),
                        r['voice_wychodzace'], r['voice_przychodzace'], r['proba_razem'], r['razem'],
                        fmt_czas(r['czas_wychodzacy_s']), fmt_czas(r['czas_przychodzacy_s']),
                        r.get('zakres_czasu', '')
                    ])
            else:
                writer.writerow(["Brak zdarzen w tym okresie."])
            writer.writerow([])

            # SEKCJA 2
            ks_b = blok['ks']
            writer.writerow(["SEKCJA 2: KONTAKTY SMS/MMS"])
            writer.writerow(["Lp", "Numer telefonu", "Imię i nazwisko / Firma",
                             "SMS wychodzące", "SMS przychodzące", "SMS razem", "Zakres czasu"])
            if not ks_b.empty:
                for i, (_, r) in enumerate(ks_b.iterrows(), 1):
                    writer.writerow([
                        i, format_numer(r['numer_kontaktu']), (r.get('nazwa_kontaktu', '') or '(brak danych)'),
                        r['sms_wychodzace'], r['sms_przychodzace'], r['sms_razem'],
                        r.get('zakres_czasu', '')
                    ])
            else:
                writer.writerow(["Brak zdarzen w tym okresie."])
            writer.writerow([])

            # SEKCJA 3
            inet_b = blok['inet']
            writer.writerow(["SEKCJA 3: INTERNET (DATA)"])
            writer.writerow(["Opis", "Ilość sesji", "Suma czasu", "Zakres czasu"])
            if inet_b['razem'] > 0:
                writer.writerow(["Internet (DATA)", inet_b["razem"], fmt_czas(inet_b["czas_s"]), inet_b["zakres_czasu"]])
            else:
                writer.writerow(["Internet (DATA)", 0, fmt_czas(0), "Brak zdarzen w tym okresie."])
            writer.writerow([])

            # SEKCJA 4
            bts_b = blok['bts']
            writer.writerow(["SEKCJA 4: STACJE BTS"])
            writer.writerow(["Lp", "Kod BTS", "Inicjujące", "Odbierające", "Adres stacji"])
            if not bts_b.empty:
                for i, (_, r) in enumerate(bts_b.iterrows(), 1):
                    writer.writerow([i, r['bts'], r['inicjujace'], r['odbierajace'],
                                     r.get('adres_bts', '') or '(brak danych)'])
            else:
                writer.writerow(["Brak zdarzen w tym okresie."])
            writer.writerow([])

            # SEKCJA 5
            imei_b = blok['imei']
            if not imei_b.empty:
                writer.writerow(["SEKCJA 5: URZĄDZENIA (IMEI)"])
                writer.writerow(["Lp", "IMEI", "Liczba zdarzeń", "Uwagi"])
                for i, (_, r) in enumerate(imei_b.iterrows(), 1):
                    writer.writerow([i, r['imei'], r['liczba_zdarzen'],
                                     "glowne" if i == 1 else ""])
                if len(imei_b) > 1:
                    writer.writerow(["UWAGA:", f"Wykryto {len(imei_b)} roznych urzadzen (IMEI) dla numeru {target}."])
                writer.writerow([])
            else:
                writer.writerow(["SEKCJA 5: URZĄDZENIA (IMEI)"])
                writer.writerow(["Brak zdarzen w tym okresie."])
                writer.writerow([])

        writer.writerow(["KONIEC RAPORTU"])


# ══════════════════════════════════════════════════════════════════════
# ANALIZA URZADZENIA (dane kluczowane po IMEI zamiast MSISDN)
# ══════════════════════════════════════════════════════════════════════
# Niektore zestawy danych opisują URZADZENIE, a nie numer: operator
# dostarcza zdarzenia, w których kluczem jest IMEI telefonu, a numery
# MSISDN występują jako numery używane w tym telefonie. Z takich danych
# powstaje raport urządzenia: jakie MSISDN były w nim użytkowane.

def _maska_strona(df, kol_strona, kol_imei, imei):
    """Wiersze, w których dana strona należy do urzadzenia (IMEI w kolumnie
    IMEI strony albo jako identyfikator strony)."""
    imei = str(imei)
    return (df[kol_imei].astype(str) == imei) | (df[kol_strona].astype(str) == imei)

def zdarzenia_urzadzenia(df, imei):
    m = _maska_strona(df, "strona_a", "imei_a", imei) | \
        _maska_strona(df, "strona_b", "imei_b", imei)
    return df[m]

def _licz_typy(s):
    return pd.Series({
        "voice": int((s == "VOICE").sum()),
        "sms_mms": int(s.isin(["SMS", "MMS"]).sum()),
        "proba": int((s == "PRÓBA").sum()),
        "data": int((s == "DATA").sum()),
    })

def numery_dla_urzadzenia(df, imei, nazwiska_map=None):
    """
    Numery MSISDN uzywane w urzadzeniu. Numer bierzemy ze strony, na ktorej
    stoi urzadzenie, o ile wyglada na MSISDN (9-12 cyfr). Gdy operator wplotal
    IMEI w kolumne identyfikatora, rekord nie zdradza numeru — trafia do
    sekcji bez numeru tylko przez IMSI/pozostale kolumny (wtedy pomijany).
    """
    sub = zdarzenia_urzadzenia(df, imei)
    czesci = []
    for kol_strona, kol_imei in (("strona_a", "imei_a"), ("strona_b", "imei_b")):
        maska = _maska_strona(sub, kol_strona, kol_imei, imei)
        wiersze = sub[maska]
        wiersze = wiersze[wiersze[kol_strona].astype(str).str.match(_RE_MSISDN, na=False)]
        if wiersze.empty:
            continue
        tmp = pd.DataFrame({
            "numer": wiersze[kol_strona].map(klucz_numer).values,
            "data": wiersze["data"].values,
            "typ": wiersze["typ"].values,
        })
        g = tmp.groupby("numer").agg(
            zdarzenia=("numer", "size"),
            od=("data", "min"),
            do=("data", "max"),
        ).reset_index()
        typy = tmp.groupby("numer")["typ"].apply(_licz_typy).unstack().reset_index()
        g = g.merge(typy, on="numer")
        czesci.append(g)
    if not czesci:
        out = pd.DataFrame(columns=[
            "numer", "zdarzenia", "od", "do", "voice", "sms_mms", "proba", "data"])
    else:
        out = pd.concat(czesci, ignore_index=True)
        agg = {"zdarzenia": "sum", "od": "min", "do": "max",
               "voice": "sum", "sms_mms": "sum", "proba": "sum", "data": "sum"}
        out = out.groupby("numer", as_index=False).agg(agg)
        out = out.sort_values("zdarzenia", ascending=False).reset_index(drop=True)
    if nazwiska_map:
        out["nazwa"] = out["numer"].map(
            lambda x: nazwiska_map.get(normalizuj_numer(x), {}).get("nazwa", ""))
    return out

def kontakty_urzadzenia(df, imei, nazwiska_map=None):
    """Numery kontaktowane PRZEZ urzadzenie (strona przeciwna)."""
    sub = zdarzenia_urzadzenia(df, imei)
    czesci = []
    for kol_strona, kol_imei, kol_drugi in (
            ("strona_a", "imei_a", "strona_b"), ("strona_b", "imei_b", "strona_a")):
        maska = _maska_strona(sub, kol_strona, kol_imei, imei)
        wiersze = sub[maska]
        wiersze = wiersze[wiersze[kol_drugi].astype(str).str.match(_RE_MSISDN, na=False)]
        if wiersze.empty:
            continue
        tmp = pd.DataFrame({
            "numer": wiersze[kol_drugi].map(klucz_numer).values,
            "data": wiersze["data"].values,
        })
        g = tmp.groupby("numer").agg(
            zdarzenia=("numer", "size"),
            od=("data", "min"),
            do=("data", "max"),
        ).reset_index()
        czesci.append(g)
    if not czesci:
        out = pd.DataFrame(columns=["numer", "zdarzenia", "od", "do"])
    else:
        out = pd.concat(czesci, ignore_index=True)
        out = out.groupby("numer", as_index=False).agg(
            {"zdarzenia": "sum", "od": "min", "do": "max"})
        out = out.sort_values("zdarzenia", ascending=False).reset_index(drop=True)
    if nazwiska_map:
        out["nazwa"] = out["numer"].map(
            lambda x: nazwiska_map.get(normalizuj_numer(x), {}).get("nazwa", ""))
    return out

def imsi_dla_urzadzenia(df, imei):
    """Karty SIM (IMSI) uzywane w urzadzeniu."""
    sub = zdarzenia_urzadzenia(df, imei)
    czesci = []
    for kol_strona, kol_imei, kol_imsi in (
            ("strona_a", "imei_a", "imsi_a"), ("strona_b", "imei_b", "imsi_b")):
        maska = _maska_strona(sub, kol_strona, kol_imei, imei)
        s = sub[maska][kol_imsi].astype(str)
        s = s[s.str.fullmatch(r"\d{10,20}", na=False)]
        czesci.append(s)
    if not czesci:
        out = pd.DataFrame(columns=["imsi", "zdarzenia"])
    else:
        all_imsi = pd.concat(czesci)
        out = all_imsi.value_counts().rename_axis("imsi").reset_index(name="zdarzenia")
    return out

def bts_dla_urzadzenia(df, imei):
    sub = zdarzenia_urzadzenia(df, imei)
    czesci = []
    for kol_strona, kol_imei, kol_bts in (
            ("strona_a", "imei_a", "bts_a"), ("strona_b", "imei_b", "bts_b")):
        maska = _maska_strona(sub, kol_strona, kol_imei, imei)
        s = sub[maska][kol_bts]
        s = s[~s.isin(NIE_BTS) & s.notna()]
        czesci.append(s)
    if not czesci:
        out = pd.DataFrame(columns=["bts", "zdarzenia"])
    else:
        all_bts = pd.concat(czesci)
        out = all_bts.value_counts().rename_axis("bts").reset_index(name="zdarzenia")
    return out


def generuj_raport_urzadzenia_txt(imei, numery_df, kontakty_df, imsi_df, bts_df,
                                  operator_nazwa, abonent, okres_od, okres_do,
                                  uwagi=None):
    L = []
    L.append("=" * 120)
    L.append("  RAPORT KONCOWY — ANALIZA URZADZENIA (IMEI)")
    L.append(f"  IMEI: {imei} | Operator: {operator_nazwa} | Zrodlo: {abonent}")
    L.append(f"  Okres danych: {okres_od} - {okres_do}")
    if uwagi:
        L.append(f"  UWAGI: {uwagi}")
    L.append("=" * 120)
    L.append("")

    # SEKCJA 1 — numery MSISDN
    L.append("-" * 120)
    L.append("  SEKCJA 1: NUMERY (MSISDN) UZYWANE W TYM URZADZENIU")
    L.append("-" * 120)
    if not numery_df.empty:
        L.append("  {:>4} {:<16} {:<32} {:>9} {:>7} {:>7} {:>7} {:>7} {:>7} {:<23}".format(
            "Lp", "Numer telefonu", "Imie i nazwisko / Firma", "Zdarzen",
            "Voice", "SMS/MMS", "Proby", "DATA", "Razem", "Zakres czasu"))
        L.append("-" * 120)
        for i, (_, r) in enumerate(numery_df.iterrows(), 1):
            nazwa = r.get('nazwa', '') or "(brak danych)"
            razem = int(r['voice'] + r['sms_mms'] + r['proba'] + r['data'])
            L.append("  {:>4} {:<16} {:<32} {:>9} {:>7} {:>7} {:>7} {:>7} {:>7} {:<23}".format(
                i, format_numer(r['numer']), nazwa[:32], r['zdarzenia'],
                r['voice'], r['sms_mms'], r['proba'], r['data'], razem,
                f'{r["od"]} - {r["do"]}'))
        L.append("")
        if len(numery_df) > 1:
            L.append(f"  UWAGA: Wykryto {len(numery_df)} roznych numerow uzywanych w urzadzeniu {imei}.")
    else:
        L.append("  Brak numerow MSISDN powiazanych z tym urzadzeniem w danych wejsciowych.")
    L.append("")

    # SEKCJA 2 — IMSI
    L.append("-" * 80)
    L.append("  SEKCJA 2: KARTY SIM (IMSI) UZYWANE W URZADZENIU")
    L.append("-" * 80)
    if not imsi_df.empty:
        L.append("  {:>4} {:<20} {:>12}".format("Lp", "IMSI", "Liczba zdarzen"))
        L.append("-" * 80)
        for i, (_, r) in enumerate(imsi_df.iterrows(), 1):
            L.append("  {:>4} {:<20} {:>12}".format(i, r['imsi'], r['zdarzenia']))
        if len(imsi_df) > 1:
            L.append("")
            L.append(f"  UWAGA: Wykryto {len(imsi_df)} roznych kart SIM (IMSI) w urzadzeniu.")
    else:
        L.append("  Brak danych IMSI.")
    L.append("")

    # SEKCJA 3 — kontakty
    L.append("-" * 120)
    L.append("  SEKCJA 3: KONTAKTY URZADZENIA (numery kontaktowane przez to urzadzenie)")
    L.append("-" * 120)
    if not kontakty_df.empty:
        L.append("  {:>4} {:<16} {:<32} {:>9} {:<23}".format(
            "Lp", "Numer telefonu", "Imie i nazwisko / Firma", "Zdarzen", "Zakres czasu"))
        L.append("-" * 120)
        for i, (_, r) in enumerate(kontakty_df.iterrows(), 1):
            nazwa = r.get('nazwa', '') or "(brak danych)"
            L.append("  {:>4} {:<16} {:<32} {:>9} {:<23}".format(
                i, format_numer(r['numer']), nazwa[:32], r['zdarzenia'],
                f'{r["od"]} - {r["do"]}'))
    else:
        L.append("  Brak zdarzen w tym okresie.")
    L.append("")

    # SEKCJA 4 — BTS
    L.append("-" * 80)
    L.append("  SEKCJA 4: STACJE BTS")
    L.append("-" * 80)
    if not bts_df.empty:
        L.append("  {:>4} {:<20} {:>12}".format("Lp", "Kod BTS", "Liczba zdarzen"))
        L.append("-" * 80)
        for i, (_, r) in enumerate(bts_df.iterrows(), 1):
            L.append("  {:>4} {:<20} {:>12}".format(i, r['bts'], r['zdarzenia']))
    else:
        L.append("  Brak zdarzen w tym okresie.")
    L.append("")
    L.append("=" * 120)
    L.append("  KONIEC RAPORTU")
    L.append("=" * 120)
    return "\n".join(L)


def generuj_raport_urzadzenia_csv(imei, numery_df, kontakty_df, imsi_df, bts_df,
                                  operator_nazwa, abonent, okres_od, okres_do,
                                  outpath, uwagi=None):
    with open(outpath, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';', quoting=csv.QUOTE_MINIMAL)
        meta = f"ANALIZA URZADZENIA (IMEI) | IMEI: {imei} | Operator: {operator_nazwa} | Zrodlo: {abonent}"
        w.writerow([meta])
        w.writerow([f"Okres danych: {okres_od} - {okres_do}"])
        if uwagi:
            w.writerow([f"UWAGI: {uwagi}"])
        w.writerow([])

        w.writerow(["SEKCJA 1: NUMERY (MSISDN) UZYWANE W URZADZENIU"])
        w.writerow(["Lp", "Numer telefonu", "Imię i nazwisko / Firma", "Zdarzeń",
                    "Voice", "SMS/MMS", "Próby", "DATA", "Razem", "Zakres od", "Zakres do"])
        if not numery_df.empty:
            for i, (_, r) in enumerate(numery_df.iterrows(), 1):
                razem = int(r['voice'] + r['sms_mms'] + r['proba'] + r['data'])
                w.writerow([i, format_numer(r['numer']), r.get('nazwa', '') or '(brak danych)',
                            r['zdarzenia'], r['voice'], r['sms_mms'], r['proba'], r['data'],
                            razem, r['od'], r['do']])
        else:
            w.writerow(["Brak numerow MSISDN powiazanych z tym urzadzeniem."])
        w.writerow([])

        w.writerow(["SEKCJA 2: KARTY SIM (IMSI)"])
        w.writerow(["Lp", "IMSI", "Liczba zdarzeń"])
        if not imsi_df.empty:
            for i, (_, r) in enumerate(imsi_df.iterrows(), 1):
                w.writerow([i, r['imsi'], r['zdarzenia']])
        else:
            w.writerow(["Brak danych IMSI."])
        w.writerow([])

        w.writerow(["SEKCJA 3: KONTAKTY URZADZENIA"])
        w.writerow(["Lp", "Numer telefonu", "Imię i nazwisko / Firma", "Zdarzeń", "Zakres od", "Zakres do"])
        if not kontakty_df.empty:
            for i, (_, r) in enumerate(kontakty_df.iterrows(), 1):
                w.writerow([i, format_numer(r['numer']), r.get('nazwa', '') or '(brak danych)',
                            r['zdarzenia'], r['od'], r['do']])
        else:
            w.writerow(["Brak zdarzen w tym okresie."])
        w.writerow([])

        w.writerow(["SEKCJA 4: STACJE BTS"])
        w.writerow(["Lp", "Kod BTS", "Liczba zdarzeń"])
        if not bts_df.empty:
            for i, (_, r) in enumerate(bts_df.iterrows(), 1):
                w.writerow([i, r['bts'], r['zdarzenia']])
        else:
            w.writerow(["Brak zdarzen w tym okresie."])
        w.writerow([])
        w.writerow(["KONIEC RAPORTU"])


# ══════════════════════════════════════════════════════════════════════
# WCZYTYWANIE DANYCH (autodetekcja, bez pytan)
# ══════════════════════════════════════════════════════════════════════

def pusty_df():
    return pd.DataFrame(columns=KOLUMNY_KANONICZNE)

def wyglada_na_imei(v):
    return bool(_RE_IMEI.fullmatch(str(v)))

def wyglada_na_msisdn(v):
    return bool(_RE_MSISDN.fullmatch(str(v)))

def wykryj_tryb_i_cel(df, msisdn, etykieta):
    """
    Zwraca (tryb, cel):
      tryb 'msisdn' -> cel = kanoniczny numer (klucz_numer),
      tryb 'imei'   -> cel = IMEI urzadzenia.
    Kolejnosc: naglowek pliku -> identyfikator strony A -> nazwa folderu.
    """
    # 1. Naglowek / parametry zadania
    if msisdn:
        raw = normalizuj_numer(msisdn)
        if wyglada_na_imei(raw) and not wyglada_na_msisdn(raw):
            return "imei", raw
        if raw:
            return "msisdn", klucz_numer(raw)
    # 2. Najczestszy identyfikator strony A w danych
    if not df.empty:
        a = df["strona_a"].dropna().astype(str)
        a = a[a.str.fullmatch(r"\d+")]
        if not a.empty:
            vc = a.value_counts()
            v = vc.index[0]
            # IMEI (14-16 cyfr) jako staly identyfikator wiekszosci zdarzen
            # -> dane kluczowane po urzadzeniu
            if wyglada_na_imei(v) and vc.iloc[0] >= max(2, int(len(a) * 0.3)):
                return "imei", v
            return "msisdn", klucz_numer(v)
    # 3. Nazwa folderu / etykieta (tylko gdy faktycznie wyglada na numer/IMEI)
    fold = normalizuj_numer(etykieta)
    if wyglada_na_msisdn(fold):
        return "msisdn", klucz_numer(fold)
    if wyglada_na_imei(fold):
        return "imei", fold
    return "msisdn", ""

def _rekord_pusty(operator, abonent, folder, uwagi):
    """Rekord dla folderu bez danych — numer brany z nazwy folderu, jesli to numer."""
    etykieta = abonent
    fold = normalizuj_numer(etykieta)
    if wyglada_na_msisdn(fold):
        tryb, cel = "msisdn", klucz_numer(fold)
    elif wyglada_na_imei(fold):
        tryb, cel = "imei", fold
    else:
        tryb, cel = "msisdn", ""
    return {
        "operator": operator, "abonent": etykieta, "numer": cel if tryb == "msisdn" else None,
        "tryb": tryb, "cel": cel, "identyfikator": "",
        "folder": folder, "df": pusty_df(), "nazwiska_map": {}, "historia": {},
        "bts_map": {}, "okres_od": "", "okres_do": "", "uwagi": uwagi,
        "zrodla": [etykieta],
    }

def wczytaj_rekordy(root, verbose=True):
    """
    Skanuje root/<operator>/<abonent>/, parsuje wszystkie zestawy danych
    i zwraca liste rekordow (poscalowanych po kluczu: MSISDN albo IMEI).

    Rekord: {operator, abonent, numer, tryb, cel, identyfikator, folder, df,
             nazwiska_map, historia, bts_map, okres_od, okres_do, uwagi, zrodla}
    """
    skan = skanuj_dane(root, verbose=verbose)
    rekordy = []

    for poz in skan:
        operator = poz["operator"]
        abonent = poz["abonent"]
        folder = poz["folder"]
        info = OPERATORZY[operator]

        try:
            zestawy = info["modul"].datasets(folder)
        except Exception as e:
            zestawy = []
            print(f"[!] {operator}/{abonent}: blad autodetekcji plikow: {e}")

        if not zestawy:
            print(f"[!] {operator}/{abonent}: brak rozpoznawalnych plikow w folderze.")
            rekordy.append(_rekord_pusty(operator, abonent, folder,
                                         "brak rozpoznawalnych plikow w folderze"))
            continue

        for zi, zestaw in enumerate(zestawy, 1):
            etykieta = abonent if len(zestawy) == 1 else f"{abonent} #{zi}"
            ramki = []
            msisdn = None
            uwagi = None

            if not zestaw.get("wykaz") and not zestaw.get("transmisja"):
                # Tylko dane abonenckie (np. zapytanie po numerze karty SIM):
                # numer MSISDN bierzemy z wierszy danych, a nie z folderu.
                numer_ab, nm_ab, hst_ab = None, {}, {}
                if zestaw.get("nazwiska") and info.get("parse_nazwiska"):
                    try:
                        nm_ab, hst_ab = info["parse_nazwiska"](zestaw["nazwiska"], verbose=False)
                        z_danymi = [n for n, w in nm_ab.items() if w.get("nazwa") or w.get("pesel")]
                        numer_ab = z_danymi[0] if z_danymi else None
                    except Exception as e:
                        print(f"    [!] {operator}/{etykieta}: blad parsowania danych abonenckich: {e}")
                if numer_ab:
                    od_ab = min([w.get("data_akt") or "9999-99-99" for w in hst_ab.get(numer_ab, [])])
                    do_ab = max([w.get("data_dezakt") or "" for w in hst_ab.get(numer_ab, [])])
                    wpis_ab = nm_ab.get(numer_ab, {})
                    rekordy.append({
                        "operator": operator, "abonent": etykieta,
                        "numer": numer_ab, "tryb": "msisdn", "cel": numer_ab,
                        "identyfikator": wpis_ab.get("pesel") or wpis_ab.get("nip") or "",
                        "folder": folder, "df": pusty_df(), "nazwiska_map": nm_ab,
                        "historia": hst_ab, "bts_map": {},
                        "okres_od": "" if od_ab == "9999-99-99" else od_ab,
                        "okres_do": do_ab,
                        "uwagi": "brak wykazu polaczen — tylko dane abonenckie "
                                 "(zapytanie po karcie SIM / numerze)",
                        "zrodla": [etykieta],
                    })
                    print(f"    -> {operator}/{etykieta}: tryb=msisdn cel={numer_ab} | "
                          f"tylko dane abonenckie | SIM: {wpis_ab.get('sim', '-')} | "
                          f"forma: {wpis_ab.get('typ_msisdn', '-')} | "
                          f"status: {wpis_ab.get('status', '-')}")
                else:
                    print(f"[!] {operator}/{etykieta}: zestaw bez plikow z danymi.")
                    rekordy.append(_rekord_pusty(operator, etykieta, folder,
                                                 "zestaw danych bez pliku wykazu"))
                continue

            if zestaw.get("wykaz"):
                if info["parse"] is None:
                    uwagi = (f"parser operatora {info['nazwa']} nie jest jeszcze dostepny — "
                             f"dostarcz przykladowy plik, aby dopasowac wzorce")
                    print(f"[!] {operator}/{etykieta}: {uwagi}")
                else:
                    try:
                        df, msisdn = info["parse"](zestaw["wykaz"], verbose=False)
                        if df is not None and not df.empty:
                            ramki.append(df)
                        elif df is not None and df.empty and msisdn:
                            uwagi = ("pusty wykaz — operator nie dostarczyl zadnych zdarzen "
                                     "dla tego numeru w objetym zapytaniem okresie")
                    except BrakParsaraError as e:
                        uwagi = str(e).split("\n")[0]
                        print(f"[!] {operator}/{etykieta}: {uwagi}")
                    except Exception as e:
                        uwagi = f"blad parsowania wykazu: {e}"
                        print(f"[!] {operator}/{etykieta}: {uwagi}")

            if zestaw.get("transmisja") and info["parse"] is not None and uwagi is None:
                try:
                    df_tr, ms_tr = info["parse"](zestaw["transmisja"], verbose=False)
                    msisdn = msisdn or ms_tr
                    if df_tr is not None and not df_tr.empty:
                        df_tr = df_tr.copy()
                        df_tr["typ"] = "DATA"
                        ramki.append(df_tr)
                except Exception as e:
                    print(f"    [!] {operator}/{etykieta}: blad parsowania transmisji: {e}")

            df = pd.concat(ramki, ignore_index=True) if ramki else pusty_df()

            if df.empty and msisdn is None:
                # Pliki byly, ale dane puste i brak numeru w naglowku.
                rekordy.append(_rekord_pusty(operator, etykieta, folder,
                                             uwagi or "pliki bez danych i bez numeru w naglowku"))
                continue

            tryb, cel = wykryj_tryb_i_cel(df, msisdn, etykieta)

            nazwiska_map, historia = {}, {}
            if zestaw.get("nazwiska") and info.get("parse_nazwiska"):
                try:
                    nazwiska_map, historia = info["parse_nazwiska"](zestaw["nazwiska"], verbose=False)
                except Exception as e:
                    print(f"    [!] {operator}/{etykieta}: blad parsowania danych abonenckich: {e}")
            bts_map = {}
            if zestaw.get("bts") and info.get("parse_bts"):
                try:
                    bts_map = info["parse_bts"](zestaw["bts"], verbose=False)
                except Exception as e:
                    print(f"    [!] {operator}/{etykieta}: blad parsowania BTS: {e}")

            od, do = okres_bilingow(df)
            wpis_ab = nazwiska_map.get(cel) or (historia.get(cel, [{}])[-1] if historia.get(cel) else {}) or {}
            identyfikator = (wpis_ab.get("pesel") or wpis_ab.get("nip") or
                             wpis_ab.get("regon") or wpis_ab.get("krs") or "")

            rekordy.append({
                "operator": operator, "abonent": etykieta,
                "numer": cel if tryb == "msisdn" else None,
                "tryb": tryb, "cel": cel, "identyfikator": identyfikator,
                "folder": folder, "df": df, "nazwiska_map": nazwiska_map,
                "historia": historia, "bts_map": bts_map,
                "okres_od": od, "okres_do": do, "uwagi": uwagi,
                "zrodla": [etykieta],
            })
            print(f"    -> {operator}/{etykieta}: tryb={tryb} cel={cel or '-'} | "
                  f"rekordow: {len(df)} | okres: {od or '-'} - {do or '-'}"
                  + (f" | UWAGI: {uwagi}" if uwagi else ""))

    # SCALANIE po kluczu (tryb, cel) — ten sam numer/IMEI moze wystapic
    # w wielu plikach/zapytaniach (imie/nazwa nie jest kluczem!).
    scalone = {}
    kolejnosc = []
    for r in rekordy:
        k = (r["tryb"], r["cel"] or f"_bez_klucza_{len(kolejnosc)}")
        if k not in scalone:
            r2 = dict(r)
            r2["nazwiska_map"] = dict(r["nazwiska_map"])
            r2["historia"] = {n: list(w) for n, w in r["historia"].items()}
            r2["bts_map"] = dict(r["bts_map"])
            r2["zrodla"] = list(r["zrodla"])
            scalone[k] = r2
            kolejnosc.append(k)
        else:
            r2 = scalone[k]
            r2["df"] = pd.concat([r2["df"], r["df"]], ignore_index=True)
            r2["nazwiska_map"].update(r["nazwiska_map"])
            for n, w in r["historia"].items():
                r2["historia"].setdefault(n, [])
                for wpis in w:
                    if wpis not in r2["historia"][n]:
                        r2["historia"][n].append(wpis)
            r2["bts_map"].update(r["bts_map"])
            if r["identyfikator"] and not r2["identyfikator"]:
                r2["identyfikator"] = r["identyfikator"]
            if r["uwagi"] and not r2["uwagi"]:
                r2["uwagi"] = r["uwagi"]
            r2["zrodla"].extend(r["zrodla"])
    for k in kolejnosc:
        r2 = scalone[k]
        if len(r2["zrodla"]) > 1:
            print(f"    [scalono] {r2['tryb']}={r2['cel']}: {len(r2['zrodla'])} zrodel -> {r2['zrodla']}")
    rekordy = [scalone[k] for k in kolejnosc]
    for r in rekordy:
        if not r["df"].empty:
            r["okres_od"], r["okres_do"] = okres_bilingow(r["df"])
        if "a_key" not in r["df"].columns:
            r["df"] = r["df"].copy()
            r["df"]["a_key"] = r["df"]["strona_a"].map(klucz_numer)
            r["df"]["b_key"] = r["df"]["strona_b"].map(klucz_numer)
    return rekordy


# ══════════════════════════════════════════════════════════════════════
# RAPORTY PER NUMER / PER URZADZENIE
# ══════════════════════════════════════════════════════════════════════

def raport_per_numer(r, outdir, txt=False):
    """Klasyczny raport dla jednego numeru MSISDN (CSV; TXT tylko gdy txt=True).
    Generowany ZAWSZE — rowniez dla pustych danych (sekcje 'Brak zdarzen')."""
    if r["tryb"] != "msisdn" or not r["cel"]:
        return None
    target = r["cel"]
    df = r["df"]
    nazwiska_map, historia, bts_map = r["nazwiska_map"], r["historia"], r["bts_map"]
    uwagi = r.get("uwagi")

    kp = kontakty_zdarzenia(df, target, nazwiska_map)
    ks = kontakty_sms(df, target, nazwiska_map)

    # Fallback: jesli nazwiska_map nie ma nazwy, ale historia ma, uzupelnij
    for numer in pd.concat([kp['numer_kontaktu'], ks['numer_kontaktu']]).unique():
        n = klucz_numer(str(numer))
        if n in historia and historia[n]:
            for wpis in historia[n]:
                if wpis.get('nazwa') and wpis['nazwa'] != "Przeniesiony do innego operatora":
                    mask_kp = kp['numer_kontaktu'].astype(str).map(klucz_numer) == n
                    mask_ks = ks['numer_kontaktu'].astype(str).map(klucz_numer) == n
                    kp.loc[mask_kp, 'nazwa_kontaktu'] = kp.loc[mask_kp, 'nazwa_kontaktu'].replace('', wpis['nazwa'])
                    ks.loc[mask_ks, 'nazwa_kontaktu'] = ks.loc[mask_ks, 'nazwa_kontaktu'].replace('', wpis['nazwa'])
                    break

    bts = bts_polaczone(df, target, bts_map)
    imei_df = imei_dla_numeru(df, target)
    inet = internet_stats(df, target)
    abonent = dane_abonenta(target, nazwiska_map)
    if not abonent.get("nazwa") and historia.get(target):
        ostatni = historia[target][-1]
        abonent = {
            "nazwa": ostatni.get("nazwa", ""),
            "adres": ostatni.get("adres", ""),
            "pesel": ostatni.get("pesel", ""),
        }
    # Dane karty SIM / formy abonamentu / statusu (Plus: dane abonenckie)
    wpis_gl = nazwiska_map.get(target, {})
    for _pole in ("sim", "typ_msisdn", "status"):
        abonent[_pole] = wpis_gl.get(_pole, "")
    okres_od, okres_do = r["okres_od"], r["okres_do"]
    if not okres_od and not df.empty:
        okres_od, okres_do = okres_bilingow(df)

    historia_abonentow = {target: list(historia[target])} if target in historia else None
    if historia_abonentow:
        historia_abonentow[target].sort(key=lambda x: x.get("data_akt", "9999-99-99") or "9999-99-99")

    historia_kontaktow = {}
    for numer in pd.concat([kp['numer_kontaktu'], ks['numer_kontaktu']]).unique():
        n = normalizuj_numer(str(numer))
        if n in historia and len(historia[n]) > 1:
            historia_kontaktow[n] = list(historia[n])
            historia_kontaktow[n].sort(key=lambda x: x.get("data_akt", "9999-99-99") or "9999-99-99")

    # --- PODZIAŁ NA BLOKI PER ABONENT (jeśli >1 zmiana właściciela) ---
    bloki = None
    if historia_abonentow and len(historia_abonentow[target]) > 1:
        wpisy = historia_abonentow[target]
        bloki = []
        for i, wpis in enumerate(wpisy):
            od = wpis.get("data_akt") or okres_od
            if i < len(wpisy) - 1:
                nast_akt = wpisy[i + 1].get("data_akt")
                dezakt = wpis.get("data_dezakt")
                if dezakt and nast_akt and dezakt < nast_akt:
                    do = (datetime.strptime(nast_akt, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
                elif dezakt:
                    do = dezakt
                else:
                    do = (datetime.strptime(nast_akt, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d") if nast_akt else okres_do
            else:
                do = okres_do

            mask = (df["data"] >= od) & (df["data"] <= do)
            df_okres = df[mask]

            kp_okres = kontakty_zdarzenia(df_okres, target, nazwiska_map)
            ks_okres = kontakty_sms(df_okres, target, nazwiska_map)
            bts_okres = bts_polaczone(df_okres, target, bts_map)
            imei_okres = imei_dla_numeru(df_okres, target)
            inet_okres = internet_stats(df_okres, target)

            abonent_okres = {
                "nazwa": wpis.get("nazwa", ""),
                "adres": wpis.get("adres", ""),
                "pesel": wpis.get("pesel", ""),
                "sim": wpis.get("sim", ""),
                "typ_msisdn": wpis.get("typ_msisdn", ""),
                "status": wpis.get("status", ""),
            }

            hk_okres = {}
            nums = pd.concat([kp_okres['numer_kontaktu'], ks_okres['numer_kontaktu']]).unique()
            for numer in nums:
                n = normalizuj_numer(str(numer))
                if n in historia_kontaktow:
                    hk_okres[n] = historia_kontaktow[n]

            naglowek = f"OKRES {i+1}: {od} – {do} | Abonent: {abonent_okres['nazwa'] or '(brak danych)'} | PESEL/REGON: {abonent_okres['pesel'] or '-'}"
            if abonent_okres['adres']:
                naglowek += f" | Adres: {abonent_okres['adres']}"

            bloki.append({
                'naglowek': naglowek,
                'kp': kp_okres, 'ks': ks_okres, 'bts': bts_okres,
                'imei': imei_okres, 'inet': inet_okres,
                'abonent': abonent_okres, 'od': od, 'do': do,
                'historia_kontaktow': hk_okres
            })

    target_dir = os.path.join(outdir, target)
    os.makedirs(target_dir, exist_ok=True)
    p_csv = os.path.join(target_dir, f"{target}_RAPORT_KONCOWY.csv")
    generuj_raport_csv(target, kp, ks, bts, imei_df, abonent, inet, okres_od, okres_do, p_csv,
                       historia_abonentow, historia_kontaktow, bloki=bloki, uwagi=uwagi)
    if txt:
        p_txt = os.path.join(target_dir, f"{target}_RAPORT_KONCOWY.txt")
        with open(p_txt, "w", encoding="utf-8") as f:
            f.write(generuj_raport_txt(target, kp, ks, bts, imei_df, abonent, inet,
                                       okres_od, okres_do, historia_abonentow,
                                       historia_kontaktow, bloki=bloki, uwagi=uwagi))
        return p_txt
    return p_csv


def raport_per_urzadzenie(r, outdir, txt=False):
    """Raport urzadzenia (IMEI): jakie numery MSISDN byly uzywane w tym telefonie.
    CSV domyslnie; TXT tylko gdy txt=True."""
    if r["tryb"] != "imei" or not r["cel"]:
        return None
    imei = r["cel"]
    df = r["df"]
    nazwiska_map = r["nazwiska_map"]
    info = OPERATORZY[r["operator"]]

    numery_df = numery_dla_urzadzenia(df, imei, nazwiska_map)
    kontakty_df = kontakty_urzadzenia(df, imei, nazwiska_map)
    imsi_df = imsi_dla_urzadzenia(df, imei)
    bts_df = bts_dla_urzadzenia(df, imei)
    okres_od, okres_do = r["okres_od"], r["okres_do"]

    target_dir = os.path.join(outdir, f"IMEI_{imei}")
    os.makedirs(target_dir, exist_ok=True)
    p_csv = os.path.join(target_dir, f"{imei}_RAPORT_URZADZENIA.csv")
    generuj_raport_urzadzenia_csv(
        imei, numery_df, kontakty_df, imsi_df, bts_df,
        info["nazwa"], r["abonent"], okres_od, okres_do, p_csv, uwagi=r.get("uwagi"))
    if txt:
        p_txt = os.path.join(target_dir, f"{imei}_RAPORT_URZADZENIA.txt")
        with open(p_txt, "w", encoding="utf-8") as f:
            f.write(generuj_raport_urzadzenia_txt(
                imei, numery_df, kontakty_df, imsi_df, bts_df,
                info["nazwa"], r["abonent"], okres_od, okres_do, uwagi=r.get("uwagi")))
        return p_txt
    return p_csv


# ══════════════════════════════════════════════════════════════════════
# ANALIZA KRZYZOWA (automatyczna, gdy >1 numer MSISDN)
# ══════════════════════════════════════════════════════════════════════

def analiza_krzyzowa(rekordy, outdir):
    """Drugi raport, powstajacy automatycznie, gdy analizowanych numerow
    MSISDN jest wiecej niz jeden."""
    import analizaKrzyzowa as ak

    msisdn_rek = [r for r in rekordy if r["tryb"] == "msisdn" and r["cel"]]
    niepuste = [r for r in rekordy if not r["df"].empty]

    bezposrednia = ak.komunikacja_bezposrednia(msisdn_rek)
    wspolne = ak.wspolne_kontakty(msisdn_rek)
    imei_df = ak.wspolne_imei(niepuste)

    out_txt = os.path.join(outdir, "RAPORT_ZBIORCZY_KRZYZOWY.txt")
    out_csv = os.path.join(outdir, "RAPORT_ZBIORCZY_KRZYZOWY.csv")
    ak.generuj_raport_zbiorczy(msisdn_rek, bezposrednia, wspolne, imei_df, out_txt, out_csv)

    print("\n" + "=" * 100)
    print("  PODSUMOWANIE ANALIZY KRZYZOWEJ (raport automatyczny)")
    print("=" * 100)
    print(f"  Abonentow (MSISDN): {len(msisdn_rek)}")
    print(f"  Bezposrednich polaczen miedzy abonentami: {len(bezposrednia)} kierunkow")
    print(f"  Wspolnych kontaktow osob trzecich: {len(wspolne)} numerow")
    print(f"  Wspolnych urzadzen (IMEI): {len(imei_df)}")
    print("=" * 100)
    print(f"\n[+] RAPORT ZBIORCZY TXT: {os.path.abspath(out_txt)}")
    print(f"[+] RAPORT ZBIORCZY CSV: {os.path.abspath(out_csv)}")


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def przebieg(dane, outdir, tylko=None, bez_krzyzowej=False, txt=False):
    if not os.path.isdir(dane):
        print(f"[!] Nie ma takiego katalogu: {dane}")
        sys.exit(1)

    print("=== Analiza bilingow — toolkit ===")
    print(f"[+] Katalog danych: {os.path.abspath(dane)}")
    rekordy = wczytaj_rekordy(dane)

    if tylko:
        k = klucz_numer(tylko)
        raw = normalizuj_numer(tylko)
        rekordy = [r for r in rekordy if r["cel"] in (k, raw)]
        if not rekordy:
            print(f"[!] Nie znaleziono numeru/IMEI '{tylko}' w danych.")
            sys.exit(1)

    if not rekordy:
        print("[!] Brak danych do analizy.")
        sys.exit(1)

    # --- PODSUMOWANIE WYKRYCIA: foldery i numery/IMEI (glowne wyjscie konsoli) ---
    numery = sorted({r["cel"] for r in rekordy if r["tryb"] == "msisdn" and r["cel"]})
    imeje = sorted({r["cel"] for r in rekordy if r["tryb"] == "imei" and r["cel"]})
    print(f"\n[+] Wykryto {len(rekordy)} zestaw(ow) danych:")
    for r in rekordy:
        op = OPERATORZY[r["operator"]]["nazwa"]
        if r["tryb"] == "imei":
            co = f"IMEI (urzadzenie) {r['cel']}"
        elif r["cel"]:
            co = f"MSISDN {format_numer(r['cel'])}"
        else:
            co = "brak numeru (raport-zalacznik)"
        uw = f" | UWAGI: {r['uwagi']}" if r.get("uwagi") else ""
        print(f"    {r['operator']}/{r['abonent']:<22} -> {co} | rekordow: {len(r['df']):>6} | "
              f"{r['okres_od'] or '-'} - {r['okres_do'] or '-'}{uw}")
    print(f"\n    Numery MSISDN ({len(numery)}): {', '.join(format_numer(n) for n in numery) if numery else '(brak)'}")
    if imeje:
        print(f"    Urzadzenia IMEI ({len(imeje)}): {', '.join(imeje)}")

    os.makedirs(outdir, exist_ok=True)

    print("\n[+] Generowanie raportow per numer / urzadzenie (CSV" + (", +TXT" if txt else "") + "):")
    for r in rekordy:
        try:
            if r["tryb"] == "imei":
                sciezka = raport_per_urzadzenie(r, outdir, txt=txt)
            else:
                sciezka = raport_per_numer(r, outdir, txt=txt)
            if sciezka:
                print(f"    raport: {sciezka}")
            else:
                print(f"    [!] {r['abonent']}: brak numeru/IMEI — raport pominiety "
                      f"({r.get('uwagi', 'brak danych identyfikujacych')})")
        except Exception as e:
            print(f"    [!] {r['abonent']}: blad raportu: {e}")

    numery = sorted({r["cel"] for r in rekordy if r["tryb"] == "msisdn" and r["cel"]})
    if len(numery) > 1 and not bez_krzyzowej:
        analiza_krzyzowa(rekordy, outdir)
    else:
        powod = "wylaczona flaga --bez-krzyzowej" if bez_krzyzowej else "analizowany jest max 1 numer MSISDN"
        print(f"\n[i] Analiza krzyzowa pominieta ({powod}).")

    print(f"\n[+] Katalog raportow: {os.path.abspath(outdir)}")


def main():
    ap = argparse.ArgumentParser(
        description="Analiza bilingow — raporty per numer (+ urzadzenia/IMEI) "
                    "i automatyczna analiza krzyzowa dla >1 numeru. Bez pytan interaktywnych.")
    ap.add_argument("--dane", default="./input",
                    help="katalog glowny ze struktura <operator>/<abonent>/ (domyslnie: ./input)")
    ap.add_argument("--outdir", default="./raport_bilingow",
                    help="katalog wyjsciowy (domyslnie: ./raport_bilingow)")
    ap.add_argument("--numer", help="ogranicz analize do jednego numeru MSISDN lub IMEI")
    ap.add_argument("--bez-krzyzowej", action="store_true",
                    help="nie generuj raportu zbiorczego analizy krzyzowej")
    ap.add_argument("--txt", action="store_true",
                    help="dodatkowo generuj raporty w formacie TXT (domyslnie tylko CSV)")
    args = ap.parse_args()
    przebieg(args.dane, args.outdir, tylko=args.numer, bez_krzyzowej=args.bez_krzyzowej,
             txt=args.txt)


if __name__ == "__main__":
    main()
