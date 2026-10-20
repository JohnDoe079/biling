#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analiza bilingow — narzedzie menu-driven, wielooperatorowe.
Wymagania systemowe (Debian/Ubuntu):
    sudo apt install poppler-utils python3-pandas
"""
import argparse
import glob
import csv
import os
import sys
from datetime import datetime, timedelta

import pandas as pd

from common import (
    autodetect_pliki, dane_abonenta, fmt_czas, input_path,
    normalizuj_numer, okres_bilingow, BLANK, NIE_BTS, NIE_IMEI, _clean_counts,
                    klucz_numer,
                    klucz_imei, klucz_numer)
from operators.orange import (parse_orange, parse_orange_nazwiska, parse_orange_bts,
                              autodetect as orange_autodetect)
from operators import orange as _orange_mod
from operators import tmobile, plus, play
from operators.base import parser_niedosteppny


# ══════════════════════════════════════════════════════════════════════
# REJESTR OPERATOROW
# ══════════════════════════════════════════════════════════════════════

OPERATORZY = {
    "orange": {
        "nazwa": "Orange Polska",
        "modul": _orange_mod,
        "autodetect": orange_autodetect,
        "parse": parse_orange,
        "parse_nazwiska": parse_orange_nazwiska,
        "parse_bts": parse_orange_bts,
    },
    "tmobile": {"nazwa": "T-Mobile Polska", "modul": tmobile, "autodetect": tmobile.autodetect,
                "parse": tmobile.parse, "parse_nazwiska": tmobile.parse_nazwiska, "parse_bts": tmobile.parse_bts},
    "plus":    {"nazwa": "Plus (Polkomtel)", "modul": plus, "autodetect": plus.autodetect,
                "parse": plus.parse_plus, "parse_nazwiska": plus.parse_plus_nazwiska, "parse_bts": plus.parse_bts},
    "play":    {"nazwa": "Play (P4)",        "modul": play, "autodetect": play.autodetect,
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

def imei_dla_numeru(df, target, nazwiska_map=None):
    """Urzadzenia (IMEI) przy numerze — z uwzglednieniem czyjego urzadzenia.
    Uwagi: 'glowne' = IMEI po stronie analizowanego numeru (jego urzadzenie);
    'kontrahent <numer> <nazwa?>' = IMEI drugiej strony polaczenia (siec przekazuje
    takze urzadzenia kontrahentow) — podajemy numer, ktory tego urzadzenia uzywal.
    IMEI grupowane po 14 cyfrach bazowych (cyfra 15=check, 16=SVN — to samo urzadzenie)."""
    sub = df[(df["strona_a"] == target) | (df["strona_b"] == target)]
    wlasne = pd.concat([
        sub[sub["strona_a"] == target]["imei_a"],
        sub[sub["strona_b"] == target]["imei_b"],
    ])
    obce = pd.concat([
        sub[(sub["strona_a"] == target) & (sub["imei_b"].notna())][["imei_b", "strona_b"]]
        .rename(columns={"imei_b": "imei", "strona_b": "numer"}),
        sub[(sub["strona_b"] == target) & (sub["imei_a"].notna())][["imei_a", "strona_a"]]
        .rename(columns={"imei_a": "imei", "strona_a": "numer"}),
    ])
    def _clean(x):
        x = x[~x.isin(NIE_IMEI) & x.notna() & (x.astype(str).str.strip() != "")]
        return x.map(klucz_imei)
    wlasne = _clean(wlasne)
    licz = {}
    for im in wlasne:
        licz[im] = licz.get(im, 0) + 1
    uwagi = {im: "glowne" for im in licz}
    if not obce.empty:
        obce = obce[obce["imei"].notna() & (obce["imei"].astype(str).str.strip() != "")
                    & ~obce["imei"].isin(NIE_IMEI)]
        obce["imei"] = obce["imei"].map(klucz_imei)
        obce["numer"] = obce["numer"].map(klucz_numer)
        for im, grp in obce.groupby("imei"):
            licz[im] = licz.get(im, 0) + len(grp)
            top = grp["numer"].value_counts()
            opisy = []
            for num, _n in top.head(3).items():
                nazwa = ""
                if nazwiska_map:
                    nazwa = (nazwiska_map.get(num, {}) or {}).get("nazwa", "")
                opisy.append(f"{num} {nazwa}".strip())
            uwagi[im] = "kontrahent: " + "; ".join(opisy)
    out = pd.DataFrame([(im, n, uwagi[im]) for im, n in licz.items()],
                       columns=["imei", "liczba_zdarzen", "uwagi"])
    return out.sort_values("liczba_zdarzen", ascending=False).reset_index(drop=True)

def ip_dla_numeru(df, target):
    """Adresy IP przydzielane numerowi w sesjach DATA — od najczesciej przyznawanych."""
    sub = df[df["typ"] == "DATA"]
    if "a_key" not in sub.columns:  # tryb reczny: brak kluczy — liczymy z stron
        sub = sub.assign(a_key=sub["strona_a"].map(klucz_numer),
                         b_key=sub["strona_b"].map(klucz_numer))
    sub = sub[(sub["a_key"] == target) | (sub["b_key"] == target)]
    if "ip" not in sub.columns:
        return pd.DataFrame(columns=["ip", "liczba_sesji"])
    ip = sub["ip"]
    ip = ip[ip.notna() & (ip.astype(str).str.strip() != "")]
    out = ip.value_counts().rename_axis("ip").reset_index(name="liczba_sesji")
    return out.sort_values("liczba_sesji", ascending=False).reset_index(drop=True)

def imsi_dla_numeru(df, target):
    """Licznik IMSI (karty SIM) uzywanych przez numer — zmiana IMSI = wymiana karty SIM."""
    sub = df[(df["strona_a"] == target) | (df["strona_b"] == target)]
    imsi_a = sub[sub["strona_a"] == target]["imsi_a"]
    imsi_b = sub[sub["strona_b"] == target]["imsi_b"]
    all_imsi = pd.concat([imsi_a, imsi_b])
    all_imsi = all_imsi[~all_imsi.isin(NIE_IMEI) & all_imsi.notna()]
    return all_imsi.value_counts().rename_axis("imsi").reset_index(name="liczba_zdarzen")

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




def _czysty_zakres(v):
    if v is None:
        return ""
    try:
        if v != v:  # NaN
            return ""
    except Exception:
        pass
    return str(v).strip()

def _z(a, b):
    """Polacz zakresy 'YYYY-MM-DD - YYYY-MM-DD' (min-max)."""
    a = _czysty_zakres(a)
    b = _czysty_zakres(b)
    if not a:
        return b
    if not b:
        return a
    a1, a2 = a.split(" - ")
    b1, b2 = b.split(" - ")
    return f"{min(a1, b1)} - {max(a2, b2)}"

def polacz_kontakty(kp, ks):
    """Sekcje 1+2: kontakty glosowe + proby + SMS/MMS w jednej tabeli."""
    k = kp.copy()
    s = ks.copy() if ks is not None else None
    if s is None or s.empty:
        for c in ("sms_wychodzace", "sms_przychodzace", "sms_razem"):
            k[c] = 0
        return k
    for c in ("sms_wychodzace", "sms_przychodzace", "sms_razem"):
        if c not in s.columns:
            s[c] = 0
    if "nazwa_kontaktu" not in s.columns:
        s["nazwa_kontaktu"] = ""
    s = s[["numer_kontaktu", "nazwa_kontaktu", "sms_wychodzace", "sms_przychodzace", "sms_razem", "zakres_czasu"]]
    for c in ("nazwa_kontaktu", "zakres_czasu"):
        if c not in k.columns:
            k[c] = ""
    m = k.merge(s, on="numer_kontaktu", how="outer", suffixes=("", "_s"))
    for c in ("voice_wychodzace", "voice_przychodzace", "proba_razem", "razem",
              "czas_wychodzacy_s", "czas_przychodzacy_s",
              "sms_wychodzace", "sms_przychodzace", "sms_razem"):
        if c in m.columns:
            m[c] = m[c].fillna(0).astype(int)  # liczby calkowite (nie 487.0)
    m["nazwa_kontaktu"] = m["nazwa_kontaktu"].fillna(m.get("nazwa_kontaktu_s", ""))
    m["zakres_czasu"] = [_z(a, b) for a, b in zip(m["zakres_czasu"], m.get("zakres_czasu_s", ""))]
    m["zakres_czasu"] = m["zakres_czasu"].fillna("")
    m["razem"] = m["razem"] + m["sms_razem"]
    m = m.drop(columns=[c for c in ("nazwa_kontaktu_s", "zakres_czasu_s") if c in m.columns])
    return m.sort_values("razem", ascending=False).reset_index(drop=True)

def generuj_raport_txt(target, kp, ks, bts, imei_df, abonent, inet, okres_od, okres_do,
                         historia_abonentow=None, historia_kontaktow=None, bloki=None, imsi_df=None, ip_df=None):
    if bloki is None:
        bloki = [{
            'naglowek': None,
            'kp': kp, 'ks': ks, 'bts': bts, 'imei': imei_df, 'inet': inet,
            'imsi': imsi_df, 'ip': ip_df,
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
    if historia_abonentow and target in historia_abonentow and len(historia_abonentow[target]) >= 1:
        from common import pelne_dane
        lines.append("-" * 120)
        lines.append("  HISTORIA ZMIAN ABONENTA")
        lines.append("-" * 120)
        lines.append("  {:>4} {:<12} {:<12} {:<36} {:<16} {:<36} {}".format(
            "Lp", "Data od", "Data do", "Nazwa / Firma", "PESEL/REGON", "Adres", "Zrodlo"))
        lines.append("-" * 120)
        for idx, wpis in enumerate(historia_abonentow[target], 1):
            lines.append("  {:>4} {:<12} {:<12} {:<36} {:<16} {:<36} {}".format(
                idx,
                (wpis.get('data_akt', '') or "-")[:12],
                (wpis.get('data_dezakt', '') or "-")[:12],
                (wpis['nazwa'] or "(brak danych)")[:36],
                (wpis['pesel'] or "-")[:16],
                (wpis['adres'] or "(brak danych)")[:36],
                (wpis.get("zrodlo", "") or "-")[:44]))
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

        # SEKCJA 1 (polaczona: glosowe + proby + SMS/MMS)
        kp_b = polacz_kontakty(blok['kp'], blok.get('ks'))
        lines.append("-" * 140)
        lines.append("  SEKCJA 1: POLACZENIA (glosowe + proby + SMS/MMS; bez FWD, DATA)")
        lines.append("-" * 140)
        if not kp_b.empty:
            lines.append("  {:>4} {:<16} {:<30} {:>6} {:>6} {:>6} {:>6} {:>6} {:>7} {:>14} {:>14} {:>22}".format(
                "Lp", "Numer telefonu", "Imie i nazwisko / Firma",
                "Swych", "Sprz", "Vwych", "Vprz", "Proby", "Razem",
                "Czas wych", "Czas przych", "Zakres czasu"))
            lines.append("-" * 140)
            for i, (_, r) in enumerate(kp_b.iterrows(), 1):
                nazwa = r.get('nazwa_kontaktu', '') or "brak danych"
                line = "  {:>4} {:<16} {:<30} {:>6} {:>6} {:>6} {:>6} {:>6} {:>7} {:>14} {:>14} {:>22}".format(
                    i, r['numer_kontaktu'], nazwa[:30],
                    int(r['sms_wychodzace']), int(r['sms_przychodzace']),
                    int(r['voice_wychodzace']), int(r['voice_przychodzace']),
                    int(r.get('proba_razem', 0)), int(r['razem']),
                    fmt_czas(r['czas_wychodzacy_s']), fmt_czas(r['czas_przychodzacy_s']),
                    r.get('zakres_czasu', ''))
                lines.append(line)
        else:
            lines.append("  Brak zdarzen w tym okresie.")
        lines.append("")

        hk = blok.get('historia_kontaktow')
        if hk:
            from common import pelne_dane
            lines.append("-" * 120)
            lines.append("  DANE OSOBOWE KONTAKTOW (numery, z ktorymi kontaktowal sie analizowany)")
            lines.append("-" * 120)
            lines.append("  {:>4} {:<16} {:<12} {:<12} {:<36} {:<16} {:<36} {}".format(
                "Lp", "Numer", "Data od", "Data do", "Nazwa / Firma", "PESEL/REGON", "Adres", "Zrodlo"))
            lines.append("-" * 120)
            global_idx = 1
            from common import klucz_sort_numer
            for numer, wpisy in sorted(hk.items(), key=lambda kv: klucz_sort_numer(kv[0])):
                for wpis in wpisy:
                    lines.append("  {:>4} {:<16} {:<12} {:<12} {:<36} {:<16} {:<36} {}".format(
                        global_idx, numer[:16],
                        (wpis.get('data_akt', '') or "-")[:12],
                        (wpis.get('data_dezakt', '') or "-")[:12],
                        (wpis['nazwa'] or "(brak danych)")[:36],
                        (wpis['pesel'] or "-")[:16],
                        (wpis['adres'] or "(brak danych)")[:36],
                        (wpis.get("zrodlo", "") or "-")[:44]))
                    global_idx += 1
            lines.append("")

        # SEKCJA 2
        inet_b = blok['inet']
        lines.append("-" * 80)
        lines.append("  SEKCJA 2: INTERNET (DATA)")
        lines.append("-" * 80)
        if inet_b['razem'] > 0:
            lines.append("  {:<24} {:>12} {:>24}".format("Opis", "Ilosc sesji", "Suma czasu"))
            lines.append("-" * 80)
            lines.append("  {:<24} {:>12} {:>24}".format(
                "Internet (DATA)", inet_b["razem"], fmt_czas(inet_b["czas_s"])))
            if inet_b["zakres_czasu"]:
                lines.append("  {:<24} {:>12} {:>24}".format("", "", inet_b["zakres_czasu"]))
            ip_b = blok.get('ip')
            if ip_b is not None and not ip_b.empty:
                lines.append("")
                lines.append("  Adresy IP (od najczesciej przyznawanych):")
                lines.append("  {:>4} {:<42} {:>12}".format("Lp", "Adres IP", "Liczba sesji"))
                lines.append("-" * 80)
                for i, (_, r) in enumerate(ip_b.iterrows(), 1):
                    lines.append("  {:>4} {:<42} {:>12}".format(i, str(r['ip'])[:42], r['liczba_sesji']))
        else:
            lines.append("  Brak zdarzen w tym okresie.")
        lines.append("")

        # SEKCJA 4
        bts_b = blok['bts']
        lines.append("-" * 100)
        lines.append("  SEKCJA 3: STACJE BTS")
        lines.append("-" * 100)
        if not bts_b.empty:
            lines.append("  {:>4} {:<20} {:>10} {:>10} {:<50}".format(
                "Lp", "Kod BTS", "Inicjujace", "Odbierajace", "Adres stacji"))
            lines.append("-" * 100)
            for i, (_, r) in enumerate(bts_b.iterrows(), 1):
                # Plus nie podaje kodu BTS — identyfikatorem jest sam adres
                kod = str(r['bts'])
                adres = r.get('adres_bts', '') or ''
                if not adres and ' ' in kod:
                    adres = kod
                line = "  {:>4} {:<20} {:>10} {:>10} {:<50}".format(
                    i, kod if ' ' not in kod else '(brak kodu)', r['inicjujace'], r['odbierajace'],
                    adres or "(brak danych)")
                lines.append(line)
        else:
            lines.append("  Brak zdarzen w tym okresie.")
        lines.append("")

        # SEKCJA 5
        imei_b = blok['imei']
        if not imei_b.empty:
            lines.append("-" * 100)
            lines.append("  SEKCJA 4: URZADZENIA (IMEI) UZYWANE PRZEZ ANALIZOWANY NUMER")
            lines.append("-" * 100)
            lines.append("  {:>4} {:<18} {:>16} {:<30}".format("Lp", "IMEI (baza 14 cyfr)", "Liczba zdarzen", "Uwagi"))
            lines.append("-" * 100)
            for i, (_, r) in enumerate(imei_b.iterrows(), 1):
                line = "  {:>4} {:<18} {:>16} {:<30}".format(i, r['imei'], r['liczba_zdarzen'], r.get('uwagi', ''))
                lines.append(line)
            _gl = imei_b[imei_b['uwagi'] == 'glowne']
            if len(_gl) > 1:
                lines.append("")
                lines.append(f"  UWAGA: Wykryto {len(_gl)} roznych urzadzen (IMEI) dla numeru {target}.")
            if 'uwagi' in imei_b.columns and (imei_b['uwagi'] == 'kontrahent').any():
                lines.append("  'kontrahent' = IMEI urzadzenia DRUGIEJ STRONY polaczenia (siec przekazuje")
                lines.append("  rowniez urzadzenia kontrahentow — NIE sa to telefony analizowanego numeru).")
            lines.append("")
        else:
            lines.append("-" * 100)
            lines.append("  SEKCJA 4: URZADZENIA (IMEI)")
            lines.append("-" * 100)
            lines.append("  Brak zdarzen w tym okresie.")
            lines.append("")

    for blok in bloki:
        # SEKCJA 6
        imsi_b = blok.get('imsi')
        if imsi_b is not None and not imsi_b.empty:
            lines.append("-" * 100)
            lines.append("  SEKCJA 5: KARTY SIM (IMSI) UZYWANE PRZEZ ANALIZOWANY NUMER")
            lines.append("-" * 100)
            lines.append("  {:>4} {:<18} {:>16} {:<30}".format("Lp", "IMSI", "Liczba zdarzen", "Uwagi"))
            lines.append("-" * 100)
            for i, (_, r) in enumerate(imsi_b.iterrows(), 1):
                uwagi = "(glowna)" if i == 1 else ""
                lines.append("  {:>4} {:<18} {:>16} {:<30}".format(i, r['imsi'], r['liczba_zdarzen'], uwagi))
            if len(imsi_b) > 1:
                lines.append("")
                lines.append(f"  UWAGA: Wykryto {len(imsi_b)} roznych kart SIM (IMSI) dla numeru {target}.")
            lines.append("")
        elif imsi_b is not None:
            lines.append("-" * 100)
            lines.append("  SEKCJA 5: KARTY SIM (IMSI)")
            lines.append("-" * 100)
            lines.append("  Brak zdarzen w tym okresie.")
            lines.append("")

    lines.append("=" * 120)
    lines.append("  KONIEC RAPORTU")
    lines.append("=" * 120)
    return "\n".join(lines)


def generuj_raport_csv(target, kp, ks, bts, imei_df, abonent, inet, okres_od, okres_do, outpath,
                       historia_abonentow=None, historia_kontaktow=None, bloki=None, imsi_df=None, ip_df=None):
    if bloki is None:
        bloki = [{
            'naglowek': None,
            'kp': kp, 'ks': ks, 'bts': bts, 'imei': imei_df, 'inet': inet,
            'imsi': imsi_df, 'ip': ip_df,
            'abonent': abonent, 'od': okres_od, 'do': okres_do,
            'historia_kontaktow': historia_kontaktow
        }]

    xlsx = str(outpath).lower().endswith(".xlsx")
    if xlsx:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        wb = Workbook()
        ws = wb.active
        ws.title = "Raport"
        writer = None
        f = None
    else:
        f = open(outpath, 'w', newline='', encoding='utf-8-sig')
        writer = csv.writer(f, delimiter=';', quoting=csv.QUOTE_MINIMAL)

    def _w(row):
        if xlsx:
            ws.append(list(row))
        else:
            writer.writerow(row)

    main_abonent = abonent if (abonent and abonent.get("nazwa")) else bloki[-1]['abonent']
    meta = f"RAPORT KONCOWY — ANALIZA BILINGOW | Numer: {target}"
    if main_abonent.get("nazwa"):
        meta += f" | Abonent: {main_abonent['nazwa']}"
    if main_abonent.get("adres"):
        meta += f" | Adres: {main_abonent['adres']}"
    if main_abonent.get("pesel"):
        meta += f" | PESEL/REGON: {main_abonent['pesel']}"
    _w([meta])
    _w([f"Okres bilingow: {okres_od} - {okres_do}"])
    _w([])

    # HISTORIA ZMIAN ABONENTA
    from common import pelne_dane
    if historia_abonentow and target in historia_abonentow and len(historia_abonentow[target]) >= 1:
        _w(["HISTORIA ZMIAN ABONENTA"])
        _w(["Lp", "Data od", "Data do", "Nazwa / Firma", "PESEL/REGON", "Adres",
                         "Dane", "Zrodlo"])
        for idx, wpis in enumerate(historia_abonentow[target], 1):
            _w([idx,
                             wpis.get('data_akt', '') or '-',
                             wpis.get('data_dezakt', '') or '-',
                             wpis['nazwa'] or '(brak danych)',
                             wpis['pesel'] or '-',
                             wpis['adres'] or '(brak danych)',
                             wpis.get("zrodlo", "") or "-"])
        _w([])

    for bi, blok in enumerate(bloki, 1):
        if blok.get('naglowek'):
            _w([blok['naglowek']])
            _w([])
        elif len(bloki) > 1:
            _w([f"OKRES {bi}: {blok['od']} – {blok['do']}"])
            _w([])

        # SEKCJA 1 (polaczona: glosowe + proby + SMS/MMS)
        kp_b = polacz_kontakty(blok['kp'], blok.get('ks'))
        _w(["SEKCJA 1: POLACZENIA (glosowe + proby + SMS/MMS; bez FWD, DATA)"])
        _w(["Lp", "Numer telefonu", "Imię i nazwisko / Firma",
                         "SMS wychodzace", "SMS przychodzace",
                         "Polaczenie wychodzace", "Polaczenie przychodzace", "Proba polaczenia",
                         "Razem", "Czas wychodzacy", "Czas przychodzacy", "Zakres czasu"])
        if not kp_b.empty:
            for i, (_, r) in enumerate(kp_b.iterrows(), 1):
                _w([
                    i, r['numer_kontaktu'], (r.get('nazwa_kontaktu', '') or 'brak danych'),
                    r['sms_wychodzace'], r['sms_przychodzace'],
                    r['voice_wychodzace'], r['voice_przychodzace'], r.get('proba_razem', 0),
                    r['razem'],
                    fmt_czas(r['czas_wychodzacy_s']), fmt_czas(r['czas_przychodzacy_s']),
                    r.get('zakres_czasu', '')
                ])
        else:
            _w(["Brak zdarzen w tym okresie."])
        _w([])

        # SEKCJA 3
        inet_b = blok['inet']
        _w(["SEKCJA 2: INTERNET (DATA)"])
        _w(["Opis", "Ilość sesji", "Suma czasu", "Zakres czasu"])
        if inet_b['razem'] > 0:
            _w(["Internet (DATA)", inet_b["razem"], fmt_czas(inet_b["czas_s"]), inet_b["zakres_czasu"]])
            ip_b = blok.get('ip')
            if ip_b is not None and not ip_b.empty:
                _w(["ADRESY IP (od najczesciej przyznawanych)", "Liczba sesji"])
                for _, r in ip_b.iterrows():
                    _w([r['ip'], r['liczba_sesji']])
        else:
            _w(["Internet (DATA)", 0, fmt_czas(0), "Brak zdarzen w tym okresie."])
        _w([])

        # SEKCJA 4
        bts_b = blok['bts']
        _w(["SEKCJA 3: STACJE BTS"])
        _w(["Lp", "Kod BTS", "Inicjujące", "Odbierające", "Adres stacji"])
        if not bts_b.empty:
            for i, (_, r) in enumerate(bts_b.iterrows(), 1):
                kod = str(r['bts'])
                adres = r.get('adres_bts', '') or ''
                if not adres and ' ' in kod:  # Plus: brak kodu, adres = identyfikator
                    adres = kod
                _w([i, kod if ' ' not in kod else '(brak kodu)',
                                 r['inicjujace'], r['odbierajace'], adres or '(brak danych)'])
        else:
            _w(["Brak zdarzen w tym okresie."])
        _w([])
        hk = blok.get('historia_kontaktow')
        if hk:
            from common import pelne_dane
            _w(["DANE OSOBOWE KONTAKTOW (numery, z ktorymi kontaktowal sie analizowany)"])
            _w(["Lp", "Numer", "Data od", "Data do", "Nazwa / Firma", "PESEL/REGON",
                             "Adres", "Dane", "Zrodlo"])
            global_idx = 1
            from common import klucz_sort_numer
            for numer, wpisy in sorted(hk.items(), key=lambda kv: klucz_sort_numer(kv[0])):
                for wpis in wpisy:
                    _w([global_idx, numer,
                                     wpis.get('data_akt', '') or '-',
                                     wpis.get('data_dezakt', '') or '-',
                                     wpis['nazwa'] or '(brak danych)',
                                     wpis['pesel'] or '-',
                                     wpis['adres'] or '(brak danych)',
                                     wpis.get("zrodlo", "") or "-"])
                    global_idx += 1
            _w([])


        # SEKCJA 5
        imei_b = blok['imei']
        if not imei_b.empty:
            _w(["SEKCJA 4: URZĄDZENIA (IMEI)"])
            _w(["Lp", "IMEI (baza 14 cyfr)", "Liczba zdarzeń", "Uwagi"])
            for i, (_, r) in enumerate(imei_b.iterrows(), 1):
                _w([i, r['imei'], r['liczba_zdarzen'], r.get('uwagi', '')])
            _gl = imei_b[imei_b['uwagi'] == 'glowne']
            if len(_gl) > 1:
                _w(["UWAGA:", f"Wykryto {len(_gl)} roznych urzadzen (IMEI) dla numeru {target}."])
            if 'uwagi' in imei_b.columns and (imei_b['uwagi'] == 'kontrahent').any():
                _w(["UWAGA:", "'kontrahent' = IMEI urzadzenia drugiej strony polaczenia (nie numeru analizowanego)."])
            _w([])
        else:
            _w(["SEKCJA 4: URZĄDZENIA (IMEI)"])
            _w(["Brak zdarzen w tym okresie."])
            _w([])

        # SEKCJA 6
        imsi_b = blok.get('imsi')
        if imsi_b is not None and not imsi_b.empty:
            _w(["SEKCJA 5: KARTY SIM (IMSI) UZYWANE PRZEZ ANALIZOWANY NUMER"])
            _w(["Lp", "IMSI", "Liczba zdarzen", "Uwagi"])
            for i, (_, r) in enumerate(imsi_b.iterrows(), 1):
                _w([i, r['imsi'], r['liczba_zdarzen'],
                                 "glowna" if i == 1 else ""])
            if len(imsi_b) > 1:
                _w(["UWAGA:", f"Wykryto {len(imsi_b)} roznych kart SIM (IMSI) dla numeru {target}."])
            _w([])
        elif imsi_b is not None:
            _w(["SEKCJA 5: KARTY SIM (IMSI)"])
            _w(["Brak zdarzen w tym okresie."])
            _w([])

    _w(["KONIEC RAPORTU"])

    if xlsx:
        bold = Font(bold=True)
        fill = PatternFill("solid", fgColor="DDDDDD")
        sekcja = ("SEKCJA", "RAPORT", "HISTORIA", "DANE", "ANALIZA")
        for row in ws.iter_rows():
            v = row[0].value
            if isinstance(v, str) and v.startswith(sekcja):
                for c in row:
                    c.font = bold
                    c.fill = fill
        for col in ws.columns:
            szer = max((len(str(c.value)) for c in col if c.value is not None), default=8)
            ws.column_dimensions[col[0].column_letter].width = min(max(szer + 2, 8), 60)
        wb.save(outpath)
    else:
        f.close()


# ══════════════════════════════════════════════════════════════════════
# RAPORT / CLI / MENU
# ══════════════════════════════════════════════════════════════════════

def najczestszy_numer(df):
    both = pd.concat([df["strona_a"], df["strona_b"]])
    both = both[both.str.match(r"^\d{6,}$", na=False)]
    return both.value_counts().idxmax()





def zgadnij_operatora_folderu(folder: str):
    """Zgaduje operatora po zawartosci folderu (pdf -> orange, xls -> plus)."""
    xls = glob.glob(os.path.join(folder, "*.xls*"))
    pdfs = glob.glob(os.path.join(folder, "*.pdf"))
    if xls and not pdfs:
        return "plus"
    if pdfs and not xls:
        return "orange"
    # mieszane/brak: pytaj wg wielkosci plikow
    return "orange" if len(pdfs) >= len(xls) else "plus"

def pliki_z_folderu(operator_key: str, folder: str):
    """
    Tryb reczny: wszystkie zestawy danego operatora w folderze scalone w JEDEN
    zestaw (wykaz + transmisja + nazwiska + bts). Zwraca (df, msisdn, nazwiska_map, historia, bts_map).
    """
    import pandas as pd
    info = OPERATORZY[operator_key]
    mod = info["modul"]
    ds = mod.datasets(folder) if hasattr(mod, "datasets") else []
    if not ds:
        return None, None, {}, {}, {}
    ramki, msisdn, msisdn_dane = [], None, None
    nazwiska_map, historia, bts_map = {}, {}, {}
    for z in ds:
        if z.get("wykaz"):
            d, ms = info["parse"](z["wykaz"])
            if ms:
                msisdn = msisdn or ms
            if d is not None and not d.empty:
                msisdn_dane = msisdn_dane or ms  # numer z zestawu, ktory MA rekordy
            ramki.append(d)
        if z.get("transmisja"):
            d2, ms2 = info["parse"](z["transmisja"])
            if ms2:
                msisdn = msisdn or ms2
            if d2 is not None and not d2.empty:
                msisdn_dane = msisdn_dane or ms2
                d2 = d2.copy()
                d2["typ"] = "DATA"
                ramki.append(d2)
        if z.get("nazwiska") and info.get("parse_nazwiska"):
            try:
                m2, h2 = info["parse_nazwiska"](z["nazwiska"])
                nazwiska_map.update(m2)
                for n, w in h2.items():
                    historia.setdefault(n, [])
                    for wp in w:
                        if wp not in historia[n]:
                            historia[n].append(wp)
            except Exception:
                pass
        if z.get("bts") and info.get("parse_bts"):
            try:
                bts_map.update(info["parse_bts"](z["bts"]))
            except Exception:
                pass
    ramki = [d for d in ramki if d is not None and not d.empty]
    df = pd.concat(ramki, ignore_index=True) if ramki else pd.DataFrame()
    if not df.empty and msisdn_dane:
        msisdn = msisdn_dane
    return df, msisdn, nazwiska_map, historia, bts_map

def uruchom(operator_key, plik, numer, outdir, plik_nazwiska=None, plik_bts=None,
            df_pre=None, nazwiska_map_pre=None, historia_pre=None, bts_map_pre=None, msisdn_pre=None):
    historia_kontaktow = {}
    info = OPERATORZY[operator_key]
    if df_pre is not None:
        df, msisdn_z_naglowka = df_pre, msisdn_pre
        print(f"\n[+] Dane wczytane z folderu ({info['nazwa']}): {len(df)} rekordow")
    else:
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
    if nazwiska_map_pre is not None:
        nazwiska_map = nazwiska_map_pre
        historia = historia_pre or {}
    parse_nazwiska = info.get("parse_nazwiska")
    if not nazwiska_map and parse_nazwiska and plik_nazwiska and os.path.exists(plik_nazwiska):
        print(f"[+] Parsowanie pliku z nazwiskami: {plik_nazwiska}")
        nazwiska_map, historia = parse_nazwiska(plik_nazwiska, verbose=True)
    if historia:
        from common import dedup_historia
        historia = {n: dedup_historia(w) for n, w in historia.items()}
        historia_abonentow = {n: w for n, w in historia.items() if len(w) > 1 or n == klucz_numer(numer)}

    if bts_map_pre is not None:
        bts_map = bts_map_pre
    else:
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
    imei_df = imei_dla_numeru(df, target, nazwiska_map)
    imsi_df = imsi_dla_numeru(df, target)
    ip_df = ip_dla_numeru(df, target)
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
    if historia_abonentow and target in historia_abonentow and len(historia_abonentow[target]) >= 1:
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
                                    historia_abonentow, historia_kontaktow, bloki=bloki, imsi_df=imsi_df,
                                    ip_df=ip_df)
    raport_txt_path = os.path.join(target_dir, f"{target}_RAPORT_KONCOWY.txt")
    with open(raport_txt_path, "w", encoding="utf-8") as f:
        f.write(raport_txt)

    raport_xlsx_path = os.path.join(target_dir, f"{target}_RAPORT_KONCOWY.xlsx")
    generuj_raport_csv(target, kp, ks, bts, imei_df, abonent, inet, okres_od, okres_do, raport_xlsx_path,
                       historia_abonentow, historia_kontaktow, bloki=bloki, imsi_df=imsi_df,
                       ip_df=ip_df)

    raport_docx_path = os.path.join(target_dir, f"{target}_RAPORT_KONCOWY.docx")
    ok_docx = generuj_raport_docx(target, kp, ks, bts, imei_df, abonent, inet, okres_od, okres_do,
                                  raport_docx_path, historia_abonentow, historia_kontaktow,
                                  bloki=bloki, imsi_df=imsi_df, ip_df=ip_df)

    print("\n" + raport_txt)
    print(f"\n[+] RAPORT KONCOWY TXT:  {os.path.abspath(raport_txt_path)}")
    print(f"[+] RAPORT KONCOWY XLSX: {os.path.abspath(raport_xlsx_path)}")
    if ok_docx:
        print(f"[+] RAPORT KONCOWY DOCX: {os.path.abspath(raport_docx_path)}")



def generuj_raport_docx(target, kp, ks, bts, imei_df, abonent, inet, okres_od, okres_do, outpath,
                        historia_abonentow=None, historia_kontaktow=None, bloki=None, imsi_df=None, ip_df=None):
    """Raport DOCX — wymaga python-docx. Zwraca True jesli wygenerowano."""
    try:
        from docx import Document
        from docx.shared import Pt
    except ImportError:
        print("[!] Brak biblioteki 'python-docx' — raport DOCX pominiety. Zainstaluj: pip install python-docx")
        return False

    doc = Document()
    doc.add_heading(f"RAPORT KONCOWY — ANALIZA BILINGOW", 0)
    doc.add_paragraph(f"Numer: {target} | Operator danych: {abonent.get('operator', '')}")
    doc.add_paragraph(f"Nazwa: {abonent.get('nazwa', '') or '(brak danych)'} | "
                      f"PESEL/REGON: {abonent.get('pesel', '') or '-'}")
    if abonent.get("adres"):
        doc.add_paragraph(f"Adres: {abonent['adres']}")
    doc.add_paragraph(f"Okres analizy: {okres_od} - {okres_do}")
    if historia_abonentow:
        doc.add_heading("HISTORIA ZMIAN ABONENTA", 1)
        for numer, wpisy in historia_abonentow.items():
            doc.add_paragraph(f"Numer {numer}:", style="List Bullet")
            for w in wpisy:
                doc.add_paragraph(
                    f"{w.get('data_akt', '')} - {w.get('data_dezakt', '') or 'obecnie'}: "
                    f"{w.get('nazwa', '')} | PESEL: {w.get('pesel', '') or '-'}", style="List Bullet 2")

    doc.add_heading("SEKCJA 1: POLACZENIA (glosowe + proby + SMS/MMS; bez FWD, DATA)", 1)
    km = polacz_kontakty(kp, ks)
    if km is not None and not km.empty:
        t = doc.add_table(rows=1, cols=9)
        t.style = "Light Grid Accent 1"
        for i, h in enumerate(["Lp", "Numer kontaktu", "Nazwa", "SMS wych", "SMS przych",
                               "V wych", "V przych", "Proby", "Razem"]):
            t.rows[0].cells[i].text = h
        for lp, (_, r) in enumerate(km.iterrows(), 1):
            c = t.add_row().cells
            c[0].text = str(lp)
            c[1].text = str(r.get("numer_kontaktu", ""))
            c[2].text = str(r.get("nazwa_kontaktu", "") or "brak danych")
            c[3].text = str(int(r.get("sms_wychodzace", 0)))
            c[4].text = str(int(r.get("sms_przychodzace", 0)))
            c[5].text = str(int(r.get("voice_wychodzace", 0)))
            c[6].text = str(int(r.get("voice_przychodzace", 0)))
            c[7].text = str(int(r.get("proba_razem", 0)))
            c[8].text = str(int(r.get("razem", 0)))
    else:
        doc.add_paragraph("Brak zdarzen w tym okresie.")

    doc.add_heading("SEKCJA 2: TRANSMISJA DANYCH (INTERNET)", 1)
    if inet:
        doc.add_paragraph(
            f"Laczna liczba sesji: {inet.get('laczna_liczba', 0)} | "
            f"Laczny czas: {fmt_czas(inet.get('laczny_czas', 0))} | "
            f"Transfer: {inet.get('laczny_transfer_mb', 0):.2f} MB")
        if ip_df is not None and not ip_df.empty:
            doc.add_paragraph("Adresy IP (od najczesciej przyznawanych):")
            t = doc.add_table(rows=1, cols=2)
            t.style = "Light Grid Accent 1"
            t.rows[0].cells[0].text = "Adres IP"
            t.rows[0].cells[1].text = "Liczba sesji"
            for _, r in ip_df.iterrows():
                c = t.add_row().cells
                c[0].text = str(r["ip"])
                c[1].text = str(r["liczba_sesji"])
    else:
        doc.add_paragraph("Brak zdarzen transmisji danych.")

    doc.add_heading("SEKCJA 3: STACJE BAZOWE (BTS)", 1)
    if bts is not None and not bts.empty:
        t = doc.add_table(rows=1, cols=4)
        t.style = "Light Grid Accent 1"
        for i, h in enumerate(["Lp", "Kod BTS", "Adres", "Liczba polaczen"]):
            t.rows[0].cells[i].text = h
        for lp, (_, r) in enumerate(bts.iterrows(), 1):
            c = t.add_row().cells
            c[0].text = str(lp)
            c[1].text = str(r.get("bts", ""))
            c[2].text = str(r.get("adres", ""))
            c[3].text = str(r.get("liczba_polaczen", ""))
    else:
        doc.add_paragraph("Brak danych BTS.")

    doc.add_heading("SEKCJA 4: URZADZENIA (IMEI)", 1)
    if imei_df is not None and not imei_df.empty:
        t = doc.add_table(rows=1, cols=4)
        t.style = "Light Grid Accent 1"
        for i, h in enumerate(["Lp", "IMEI (baza 14 cyfr)", "Liczba zdarzen", "Uwagi"]):
            t.rows[0].cells[i].text = h
        for lp, (_, r) in enumerate(imei_df.iterrows(), 1):
            c = t.add_row().cells
            c[0].text = str(lp)
            c[1].text = str(r["imei"])
            c[2].text = str(r["liczba_zdarzen"])
            c[3].text = str(r.get("uwagi", ""))
        _gl = imei_df[imei_df['uwagi'] == 'glowne']
        if len(_gl) > 1:
            doc.add_paragraph(f"UWAGA: Wykryto {len(_gl)} roznych urzadzen (IMEI) dla numeru {target}.")
        if 'uwagi' in imei_df.columns and (imei_df['uwagi'] == 'kontrahent').any():
            doc.add_paragraph("'kontrahent' = IMEI urzadzenia drugiej strony polaczenia (nie numeru analizowanego).")
    else:
        doc.add_paragraph("Brak danych IMEI.")

    doc.add_heading("SEKCJA 5: KARTY SIM (IMSI)", 1)
    if imsi_df is not None and not imsi_df.empty:
        t = doc.add_table(rows=1, cols=3)
        t.style = "Light Grid Accent 1"
        for i, h in enumerate(["Lp", "IMSI", "Liczba zdarzen"]):
            t.rows[0].cells[i].text = h
        for lp, (_, r) in enumerate(imsi_df.iterrows(), 1):
            c = t.add_row().cells
            c[0].text = str(lp)
            c[1].text = str(r["imsi"])
            c[2].text = str(r["liczba_zdarzen"])
        if len(imsi_df) > 1:
            doc.add_paragraph(f"UWAGA: Wykryto {len(imsi_df)} roznych kart SIM (IMSI) dla numeru {target}.")
    else:
        doc.add_paragraph("Brak danych IMSI.")

    doc.save(outpath)
    return True

def domyslny_outdir():
    """output/RRRR-MM-DD_GGMM — folder wynikowy nazwany data + godzina."""
    from datetime import datetime
    return os.path.join("./output", datetime.now().strftime("%Y-%m-%d_%H%M"))


def main():
    ap = argparse.ArgumentParser(description="Analiza bilingow — autodetekcja")
    ap.add_argument("--folder", help="pojedynczy folder abonenta (automatycznie input/<operator>/<abonent>)")
    ap.add_argument("--numer", help="numer analizowany (domyslnie: auto-detekcja z naglowka)")
    ap.add_argument("--outdir", default=None, help="folder wynikowy (domyslnie: output/RRRR-MM-DD_GGMM)")
    ap.add_argument("--dane", default="./input", help="katalog glowny z danymi (domyslnie: ./input)")
    args = ap.parse_args()
    if not args.outdir:
        args.outdir = domyslny_outdir()

    print("=== Analiza bilingow — toolkit (autodetekcja) ===")

    # Tryb 1: pojedynczy folder
    if args.folder:
        if not os.path.isdir(args.folder):
            print(f"[!] Podana sciezka nie jest folderem: {args.folder}")
            sys.exit(1)
        operator_key = zgadnij_operatora_folderu(args.folder)
        df_f, ms_f, naz_f, hist_f, bts_f = pliki_z_folderu(operator_key, args.folder)
        if df_f is None or (df_f.empty and not ms_f):
            print(f"[!] Nie znaleziono danych operatora '{operator_key}' w: {args.folder}")
            sys.exit(1)
        uruchom(operator_key, None, args.numer, args.outdir,
                df_pre=df_f, nazwiska_map_pre=naz_f or {}, historia_pre=hist_f or {},
                bts_map_pre=bts_f or {}, msisdn_pre=ms_f)
        return

    # Tryb 2: autodetekcja ./input
    if not os.path.isdir(args.dane):
        print(f"[!] Brak katalogu {args.dane} — umiesc dane w strukturze <operator>/<abonent>/")
        sys.exit(1)
    from common import skanuj_dane
    pozycje = skanuj_dane(args.dane, verbose=False)
    if not pozycje:
        print(f"[!] Brak danych w {args.dane} — umiesc podfoldery abonentow w input/<operator>/")
        sys.exit(1)

    print(f"\n[+] Wykryto dane w {args.dane}: {len(pozycje)} folderow abonentow.")
    for p in pozycje[:20]:
        print(f"    - {p['operator']}/{p['abonent']}")
    if len(pozycje) > 20:
        print(f"    ... i {len(pozycje)-20} kolejnych")

    while True:
        odp = input("\nAnalizowac wszystkich (analiza krzyzowa)? [t/n]: ").strip().lower()
        if odp in ("t", "tak", "y", "yes") or odp == "":
            if odp == "":
                print("(Enter = analiza wszystkich)")
            import analizaKrzyzowa
            analizaKrzyzowa.przebieg(args.dane, args.outdir)
            return
        if odp in ("n", "nie"):
            break

    print("\nWybierz folder do analizy pojedynczego abonenta:")
    for idx, p in enumerate(pozycje, 1):
        print(f"  [{idx}] {p['operator']}/{p['abonent']}")
    while True:
        odp = input("Wybierz folder [1-%d] (pusty Enter = koniec): " % len(pozycje)).strip().lower()
        if odp == "":
            print("[!] Konczymy.")
            sys.exit(0)
        if odp.isdigit() and 1 <= int(odp) <= len(pozycje):
            wybr = pozycje[int(odp) - 1]
            df_f, ms_f, naz_f, hist_f, bts_f = pliki_z_folderu(wybr["operator"], wybr["folder"])
            if df_f is None or (df_f.empty and not ms_f):
                print("[!] Brak danych w tym folderze.")
                continue
            uruchom(wybr["operator"], None, args.numer, args.outdir,
                    df_pre=df_f, nazwiska_map_pre=naz_f or {}, historia_pre=hist_f or {},
                    bts_map_pre=bts_f or {}, msisdn_pre=ms_f)
            return
        print("  Nieprawidlowy wybor.")


if __name__ == "__main__":
    main()
