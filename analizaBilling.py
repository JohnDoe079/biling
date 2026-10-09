#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analiza bilingow — narzedzie menu-driven, wielooperatorowe.
Wymagania systemowe (Debian/Ubuntu):
    sudo apt install poppler-utils python3-pandas
"""
import argparse
import csv
import os
import sys
from datetime import datetime, timedelta

import pandas as pd

from common import (
    autodetect_pliki, dane_abonenta, fmt_czas, input_path,
    normalizuj_numer, okres_bilingow, BLANK, NIE_BTS, NIE_IMEI, _clean_counts
)
from operators.orange import (parse_orange, parse_orange_nazwiska, parse_orange_bts,
                              autodetect as orange_autodetect)
from operators import tmobile, plus, play
from operators.base import parser_niedosteppny


# ══════════════════════════════════════════════════════════════════════
# REJESTR OPERATOROW
# ══════════════════════════════════════════════════════════════════════

OPERATORZY = {
    "orange": {
        "nazwa": "Orange Polska",
        "autodetect": orange_autodetect,
        "parse": parse_orange,
        "parse_nazwiska": parse_orange_nazwiska,
        "parse_bts": parse_orange_bts,
    },
    "tmobile": {"nazwa": "T-Mobile Polska", "autodetect": tmobile.autodetect,
                "parse": tmobile.parse, "parse_nazwiska": tmobile.parse_nazwiska, "parse_bts": tmobile.parse_bts},
    "plus":    {"nazwa": "Plus (Polkomtel)", "autodetect": plus.autodetect,
                "parse": plus.parse, "parse_nazwiska": plus.parse_nazwiska, "parse_bts": plus.parse_bts},
    "play":    {"nazwa": "Play (P4)",        "autodetect": play.autodetect,
                "parse": play.parse, "parse_nazwiska": play.parse_nazwiska, "parse_bts": play.parse_bts},
}


# ══════════════════════════════════════════════════════════════════════
# ANALIZA
# ══════════════════════════════════════════════════════════════════════

def kontakty_zdarzenia(df, target, nazwiska_map=None):
    voice = df[df["typ"] == "VOICE"]
    proba = df[df["typ"] == "PRÓBA"]
    wych = voice[voice["strona_a"] == target].groupby("strona_b").agg(
        voice_wychodzace=("strona_b", "size"),
        czas_wychodzacy_s=("czas_trwania", "sum"))
    przych = voice[voice["strona_b"] == target].groupby("strona_a").agg(
        voice_przychodzace=("strona_a", "size"),
        czas_przychodzacy_s=("czas_trwania", "sum"))
    proba_wych = proba[proba["strona_a"] == target].groupby("strona_b").size()
    proba_wych.name = "proba_wych"
    proba_przych = proba[proba["strona_b"] == target].groupby("strona_a").size()
    proba_przych.name = "proba_przych"
    proba_df = pd.concat([proba_wych, proba_przych], axis=1).fillna(0).astype(int)
    proba_df["proba_razem"] = proba_df["proba_wych"] + proba_df["proba_przych"]
    sub = pd.concat([voice, proba])
    a_rows = sub[sub["strona_a"] == target][["strona_b", "data"]].rename(columns={"strona_b": "numer"})
    b_rows = sub[sub["strona_b"] == target][["strona_a", "data"]].rename(columns={"strona_a": "numer"})
    all_rows = pd.concat([a_rows, b_rows])
    if not all_rows.empty:
        zakres = all_rows.groupby("numer")["data"].agg(["min", "max"])
        zakres["zakres_czasu"] = zakres["min"] + " - " + zakres["max"]
    else:
        zakres = pd.DataFrame(columns=["min", "max", "zakres_czasu"])
    out = wych.join(przych, how="outer").fillna(0)
    out = out.join(proba_df[["proba_razem"]], how="outer").fillna(0)
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
    msg = df[df["typ"].isin(["SMS", "MMS"])]
    wych = msg[msg["strona_a"] == target].groupby("strona_b").size()
    wych.name = "sms_wychodzace"
    przych = msg[msg["strona_b"] == target].groupby("strona_a").size()
    przych.name = "sms_przychodzace"
    out = pd.concat([wych, przych], axis=1).fillna(0).astype(int)
    out["sms_razem"] = out["sms_wychodzace"] + out["sms_przychodzace"]
    a_rows = msg[msg["strona_a"] == target][["strona_b", "data"]].rename(columns={"strona_b": "numer"})
    b_rows = msg[msg["strona_b"] == target][["strona_a", "data"]].rename(columns={"strona_a": "numer"})
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
    sub_a = df[df["strona_a"] == target]
    sub_b = df[df["strona_b"] == target]
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
    sub = df[(df["strona_a"] == target) | (df["strona_b"] == target)]
    imei_a = sub[sub["strona_a"] == target]["imei_a"]
    imei_b = sub[sub["strona_b"] == target]["imei_b"]
    all_imei = pd.concat([imei_a, imei_b])
    all_imei = all_imei[~all_imei.isin(NIE_IMEI) & all_imei.notna()]
    return all_imei.value_counts().rename_axis("imei").reset_index(name="liczba_zdarzen")

def internet_stats(df, target):
    data = df[df["typ"] == "DATA"]
    wych = data[data["strona_a"] == target]
    przych = data[data["strona_b"] == target]
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


# ══════════════════════════════════════════════════════════════════════
# RAPORTY
# ══════════════════════════════════════════════════════════════════════

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


def generuj_raport_txt(target, kp, ks, bts, imei_df, abonent, inet, okres_od, okres_do,
                         historia_abonentow=None, historia_kontaktow=None, bloki=None):
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
    meta = f"  Numer: {target}"
    if main_abonent.get("nazwa"):
        meta += f" | Abonent: {main_abonent['nazwa']}"
    if main_abonent.get("adres"):
        meta += f" | Adres: {main_abonent['adres']}"
    if main_abonent.get("pesel"):
        meta += f" | PESEL/REGON: {main_abonent['pesel']}"
    lines.append(meta)
    lines.append(f"  Okres bilingow: {okres_od} - {okres_do}")
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
                        global_idx, numer[:16],
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
                elif nazwa == "Przeniesiony do innego operatora":
                    nazwa = "Przeniesiony do innego operatora"
                line = "  {:>4} {:<16} {:<32} {:>8} {:>8} {:>8} {:>8} {:>18} {:>18} {:>22}".format(
                    i, r['numer_kontaktu'], nazwa[:32],
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
                elif nazwa == "Przeniesiony do innego operatora":
                    nazwa = "Przeniesiony do innego operatora"
                line = "  {:>4} {:<16} {:<32} {:>6} {:>6} {:>6} {:>22}".format(
                    i, r['numer_kontaktu'], nazwa[:32],
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
                uwagi = "(glowne)" if i == 1 else ""
                line = "  {:>4} {:<18} {:>16} {:<30}".format(i, r['imei'], r['liczba_zdarzen'], uwagi)
                lines.append(line)
            if len(imei_b) > 1:
                lines.append("")
                lines.append(f"  UWAGA: Wykryto {len(imei_b)} roznych urzadzen (IMEI) dla numeru {target}.")
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
                       historia_abonentow=None, historia_kontaktow=None, bloki=None):
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
        meta = f"RAPORT KONCOWY — ANALIZA BILINGOW | Numer: {target}"
        if main_abonent.get("nazwa"):
            meta += f" | Abonent: {main_abonent['nazwa']}"
        if main_abonent.get("adres"):
            meta += f" | Adres: {main_abonent['adres']}"
        if main_abonent.get("pesel"):
            meta += f" | PESEL/REGON: {main_abonent['pesel']}"
        writer.writerow([meta])
        writer.writerow([f"Okres bilingow: {okres_od} - {okres_do}"])
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
                        writer.writerow([global_idx, numer,
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
                        i, r['numer_kontaktu'], (r.get('nazwa_kontaktu', '') or '(brak danych)'),
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
                        i, r['numer_kontaktu'], (r.get('nazwa_kontaktu', '') or '(brak danych)'),
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
# RAPORT / CLI / MENU
# ══════════════════════════════════════════════════════════════════════

def najczestszy_numer(df):
    both = pd.concat([df["strona_a"], df["strona_b"]])
    both = both[both.str.match(r"^\d{6,}$", na=False)]
    return both.value_counts().idxmax()

def uruchom(operator_key, plik, numer, outdir, plik_nazwiska=None, plik_bts=None):
    historia_kontaktow = {}
    info = OPERATORZY[operator_key]
    print(f"\n[+] Parsowanie pliku ({info['nazwa']}): {plik}")
    df, msisdn_z_naglowka = info["parse"](plik, verbose=True)
    if df.empty:
        print("[!] Nie udalo sie sparsowac zadnego rekordu z pliku. Sprawdz format.")
        return
    print(f"[+] Sparsowano {len(df)} rekordow.")
    target = numer or msisdn_z_naglowka or najczestszy_numer(df)
    print(f"[+] Numer analizowany: {target}")

    nazwiska_map = {}
    historia = {}
    historia_abonentow = {}
    parse_nazwiska = info.get("parse_nazwiska")
    if parse_nazwiska and plik_nazwiska and os.path.exists(plik_nazwiska):
        print(f"[+] Parsowanie pliku z nazwiskami: {plik_nazwiska}")
        nazwiska_map, historia = parse_nazwiska(plik_nazwiska, verbose=True)
        historia_abonentow = historia

    bts_map = {}
    parse_bts = info.get("parse_bts")
    if parse_bts and plik_bts and os.path.exists(plik_bts):
        print(f"[+] Parsowanie pliku z adresami BTS: {plik_bts}")
        bts_map = parse_bts(plik_bts, verbose=True)

    kp = kontakty_zdarzenia(df, target, nazwiska_map)
    ks = kontakty_sms(df, target, nazwiska_map)

    # Fallback: jesli nazwiska_map nie ma nazwy, ale historia ma, uzupelnij
    for numer in pd.concat([kp['numer_kontaktu'], ks['numer_kontaktu']]).unique():
        n = normalizuj_numer(str(numer))
        if n in historia and historia[n]:
            for wpis in historia[n]:
                if wpis.get('nazwa') and wpis['nazwa'] != "Przeniesiony do innego operatora":
                    kp.loc[kp['numer_kontaktu'].astype(str).map(normalizuj_numer) == n, 'nazwa_kontaktu'] = \
                        kp.loc[kp['numer_kontaktu'].astype(str).map(normalizuj_numer) == n, 'nazwa_kontaktu'].replace('', wpis['nazwa'])
                    ks.loc[ks['numer_kontaktu'].astype(str).map(normalizuj_numer) == n, 'nazwa_kontaktu'] = \
                        ks.loc[ks['numer_kontaktu'].astype(str).map(normalizuj_numer) == n, 'nazwa_kontaktu'].replace('', wpis['nazwa'])
                    break

    bts = bts_polaczone(df, target, bts_map)
    imei_df = imei_dla_numeru(df, target)
    inet = internet_stats(df, target)
    abonent = dane_abonenta(target, nazwiska_map)
    okres_od, okres_do = okres_bilingow(df)

    # Sortuj historie chronologicznie (od najstarszego)
    if historia_abonentow and target in historia_abonentow:
        historia_abonentow[target].sort(key=lambda x: x.get("data_akt", "9999-99-99") or "9999-99-99")

    # Historia zmian dla numerow kontaktowych
    if historia:
        for numer in pd.concat([kp['numer_kontaktu'], ks['numer_kontaktu']]).unique():
            n = normalizuj_numer(str(numer))
            if n in historia and len(historia[n]) > 1:
                historia_kontaktow[n] = historia[n]
                historia_kontaktow[n].sort(key=lambda x: x.get("data_akt", "9999-99-99") or "9999-99-99")

    # Statystyki aktywnosci per okres abonenta (dla target numeru)
    if historia_abonentow and target in historia_abonentow:
        for wpis in historia_abonentow[target]:
            od = wpis.get("data_akt", "")
            do = wpis.get("data_dezakt", "")
            wpis["stats"] = stats_dla_okresu(df, target, od, do)

    # --- PODZIAŁ NA BLOKI PER ABONENT (jeśli >1 zmiana) ---
    bloki = None
    if historia_abonentow and target in historia_abonentow and len(historia_abonentow[target]) > 1:
        wpisy = historia_abonentow[target]
        bloki = []
        for i, wpis in enumerate(wpisy):
            od = wpis.get("data_akt") or okres_od
            if i < len(wpisy) - 1:
                nast_akt = wpisy[i + 1].get("data_akt")
                dezakt = wpis.get("data_dezakt")
                if dezakt and dezakt < nast_akt:
                    # Luka między dezaktywacją a następnym abonentem — przypisujemy do tego abonenta
                    do = (datetime.strptime(nast_akt, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
                else:
                    if dezakt:
                        do = dezakt
                    else:
                        do = (datetime.strptime(nast_akt, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
            else:
                # Ostatni abonent: od aktywacji do końca billingów (ignoruj dezaktywację)
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
            }

            hk_okres = {}
            if historia_kontaktow:
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

    raport_txt = generuj_raport_txt(target, kp, ks, bts, imei_df, abonent, inet, okres_od, okres_do,
                                    historia_abonentow, historia_kontaktow, bloki=bloki)
    raport_txt_path = os.path.join(target_dir, f"{target}_RAPORT_KONCOWY.txt")
    with open(raport_txt_path, "w", encoding="utf-8") as f:
        f.write(raport_txt)

    raport_csv_path = os.path.join(target_dir, f"{target}_RAPORT_KONCOWY.csv")
    generuj_raport_csv(target, kp, ks, bts, imei_df, abonent, inet, okres_od, okres_do, raport_csv_path,
                       historia_abonentow, historia_kontaktow, bloki=bloki)

    print("\n" + raport_txt)
    print(f"\n[+] RAPORT KONCOWY TXT: {os.path.abspath(raport_txt_path)}")
    print(f"[+] RAPORT KONCOWY CSV: {os.path.abspath(raport_csv_path)}")


def wybierz_operatora_interaktywnie():
    klucze = list(OPERATORZY.keys())
    print("\nDostepni operatorzy:")
    for i, k in enumerate(klucze, 1):
        print(f"  [{i}] {OPERATORZY[k]['nazwa']}")
    while True:
        wyb = input(f"Wybierz operatora [1-{len(klucze)}]: ").strip()
        if wyb.isdigit() and 1 <= int(wyb) <= len(klucze):
            return klucze[int(wyb) - 1]
        print("Nieprawidlowy wybor.")

def zapytaj_o_plik(opis):
    while True:
        odp = input(f"\nCzy posiadasz plik z {opis}? [t/n]: ").strip().lower()
        if odp in ("n", "nie", "no", ""):
            print(f"  -> Pominieto plik z {opis}.")
            return None
        if odp in ("t", "tak", "yes", "y"):
            sciezka = input_path(f"  Podaj sciezke do pliku z {opis}: ").strip()
            if os.path.exists(sciezka):
                return sciezka
            print(f"  [!] Plik nie istnieje: {sciezka}. Sprobuj ponownie lub pomin.")
            continue
        print("  Wpisz 't' (tak) lub 'n' (nie).")

def main():
    ap = argparse.ArgumentParser(description="Analiza bilingow")
    ap.add_argument("--operator", choices=list(OPERATORZY.keys()))
    ap.add_argument("--plik", help="glowny plik z wykazem polaczen (PDF)")
    ap.add_argument("--plik-nazwiska", help="PDF z nazwiskami / firmami")
    ap.add_argument("--plik-bts", help="PDF z adresami stacji BTS")
    ap.add_argument("--numer", help="numer analizowany (domyslnie: auto-detekcja)")
    ap.add_argument("--outdir", default="./raport_bilingow")
    ap.add_argument("--folder", help="folder z plikami Orange (autodetekcja *_wykaz.pdf, *_daneOsobowe.pdf, *_bts.pdf)")
    args = ap.parse_args()

    # Autodetekcja plikow z folderu
    if args.folder:
        if not os.path.isdir(args.folder):
            print(f"[!] Podana sciezka nie jest folderem: {args.folder}")
            sys.exit(1)
        plik, plik_nazwiska, plik_bts = autodetect_pliki(args.folder)
        if not plik:
            print(f"[!] Nie znaleziono pliku *_wykaz.pdf w folderze: {args.folder}")
            sys.exit(1)
        print(f"[+] Autodetekcja w folderze: {args.folder}")
        print(f"    Wykaz: {plik or '-'}")
        print(f"    Dane osobowe: {plik_nazwiska or '-'}")
        print(f"    BTS: {plik_bts or '-'}")
        operator_key = args.operator or "orange"
        uruchom(operator_key, plik, args.numer, args.outdir,
                plik_nazwiska=plik_nazwiska, plik_bts=plik_bts)
        return

    if args.operator and args.plik:
        uruchom(args.operator, args.plik, args.numer, args.outdir,
                plik_nazwiska=args.plik_nazwiska, plik_bts=args.plik_bts)
        return

    print("=== Analiza bilingow — toolkit ===")
    operator_key = args.operator or wybierz_operatora_interaktywnie()

    plik = args.plik
    plik_nazwiska = args.plik_nazwiska
    plik_bts = args.plik_bts

    if not plik:
        while True:
            sciezka = input_path("\nPodaj sciezke do pliku z wykazem polaczen (lub folderu z plikami PDF): ").strip()
            if os.path.isdir(sciezka):
                plik_auto, plik_nazwiska_auto, plik_bts_auto = autodetect_pliki(sciezka)
                if plik_auto:
                    print(f"[+] Wykryto folder. Autodetekcja plikow:")
                    print(f"    Wykaz: {plik_auto}")
                    if plik_nazwiska_auto:
                        print(f"    Dane osobowe: {plik_nazwiska_auto}")
                    if plik_bts_auto:
                        print(f"    BTS: {plik_bts_auto}")
                    plik = plik_auto
                    if not plik_nazwiska:
                        plik_nazwiska = plik_nazwiska_auto
                    if not plik_bts:
                        plik_bts = plik_bts_auto
                    break
                else:
                    print(f"[!] W folderze nie znaleziono pliku *_wykaz.pdf.")
                    continue
            elif os.path.exists(sciezka):
                plik = sciezka
                break
            print(f"[!] Sciezka nie istnieje: {sciezka}")

    if plik_nazwiska is None and not args.plik:
        plik_nazwiska = zapytaj_o_plik("nazwiskami / firmami przypisanymi do numerow")

    if plik_bts is None and not args.plik:
        plik_bts = zapytaj_o_plik("adresami stacji BTS")

    numer = args.numer or input("\nNumer analizowany (Enter = auto-detekcja): ").strip() or None
    outdir = input(f"\nKatalog wyjsciowy [{args.outdir}]: ").strip() or args.outdir

    uruchom(operator_key, plik, numer, outdir,
            plik_nazwiska=plik_nazwiska, plik_bts=plik_bts)

if __name__ == "__main__":
    main()
