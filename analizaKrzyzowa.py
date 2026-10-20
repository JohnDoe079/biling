#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analiza krzyzowa bilingow — multi-operator, multi-abonent.

Struktura danych:
    ROOT/<operator>/<abonent>/...pliki...

operator   = orange | tmobile | plus | play
abonent    = dowolna nazwa folderu (najlepiej: nazwisko / nazwa firmy / numer)

Co robi:
  1. Parsuje wszystkich abonentow ze wszystkich operatorow.
  2. Generuje klasyczny raport per numer (do podfolderow outdir/<numer>/).
  3. Generuje raport zbiorczy z analiza krzyzowa:
     - komunikacja bezposrednia miedzy analizowanymi abonentami,
     - wspolne kontakty osob trzecich (lacza pary abonentow),
     - wspolne urzadzenia (IMEI) wystepujace w billingach roznych abonentow.

Uzycie:
    python3 analizaKrzyzowa.py --dane ./dane --outdir ./raport_krzyzowy
    python3 analizaKrzyzowa.py            # tryb interaktywny
"""
import argparse
import csv
import itertools
import os
import sys
from datetime import datetime

import pandas as pd

from common import (
    skanuj_dane, klucz_numer, normalizuj_numer, fmt_czas, input_path,
    dane_abonenta, okres_bilingow, BLANK, NIE_IMEI, _clean_counts,
)
from operators import orange, tmobile, plus, play
from operators.base import BrakParsaraError
import analizaBilling as ab


# ══════════════════════════════════════════════════════════════════════
# REJESTR OPERATOROW
# ══════════════════════════════════════════════════════════════════════

OPERATORZY = {
    "orange": {
        "nazwa": "Orange Polska",
        "modul": orange,
        "parse": orange.parse_orange,
        "parse_nazwiska": orange.parse_orange_nazwiska,
        "parse_bts": orange.parse_orange_bts,
    },
    "tmobile": {"nazwa": "T-Mobile Polska", "modul": tmobile},
    "plus":    {"nazwa": "Plus (Polkomtel)", "modul": plus,
            "parse": plus.parse_plus, "parse_nazwiska": plus.parse_plus_nazwiska},
    "play":    {"nazwa": "Play (P4)",        "modul": play},
}


# ══════════════════════════════════════════════════════════════════════
# WCZYTYWANIE DANYCH
# ══════════════════════════════════════════════════════════════════════

def wykryj_numer_abonenta(df, msisdn, nazwa_folderu):
    """Numer abonenta: MSISDN z naglowka > nazwa folderu jesli to numer > najczestszy numer."""
    if msisdn:
        return klucz_numer(msisdn)
    fold = klucz_numer(nazwa_folderu)
    if fold and len(fold) >= 9:
        return fold
    both = pd.concat([df["strona_a"], df["strona_b"]])
    both = both[both.astype(str).str.match(r"^\d{6,}$", na=False)]
    if both.empty:
        return ""
    return klucz_numer(both.value_counts().idxmax())


def wczytaj_wszystkie(root: str, verbose: bool = True):
    """
    Zwraca (rekordy, global_df).
    rekordy: [{operator, abonent, numer, folder, df, nazwiska_map, historia, bts_map, okres_od, okres_do}]
    global_df: wszystkie zdarzenia + kolumny abonent, operator, a_key, b_key.
    """
    skan = skanuj_dane(root, verbose=verbose)
    rekordy = []
    ramki = []

    for poz in skan:
        operator = poz["operator"]
        info = OPERATORZY[operator]
        folder = poz["folder"]
        abonent = poz["abonent"]

        try:
            zestawy = info["modul"].datasets(folder)
        except Exception as e:
            print(f"[!] {operator}/{abonent}: blad autodetekcji: {e}")
            continue

        for zi, zestaw in enumerate(zestawy, 1):
            etykieta = abonent if len(zestawy) == 1 else f"{abonent} #{zi}"
            if verbose and zestaw.get("wykaz"):
                print(f"\n[+] {operator}/{etykieta}")
                for rola in ("wykaz", "transmisja", "nazwiska", "bts"):
                    if zestaw.get(rola):
                        print(f"    {rola}: {os.path.basename(zestaw[rola])}")

            # Pliki z SAMYMI danymi abonenckimi (bez wykazu) NIE sa pomijane:
            # ich mapa zostaje dolaczona do rekordu o tym samym MSISDN
            # (operator rozbija jeden numer na kilka tokenow).
            dane_mapa, dane_hist = {}, {}
            msisdn_dane = None
            if zestaw.get("nazwiska") and info.get("parse_nazwiska"):
                try:
                    dane_mapa, dane_hist = info["parse_nazwiska"](zestaw["nazwiska"], verbose=False)
                except Exception as e:
                    print(f"    [!] blad parsowania danych abonenckich: {e}")

            if not zestaw.get("wykaz") and not zestaw.get("transmisja"):
                if zestaw.get("nazwiska") and info.get("parse_nazwiska"):
                    # probujmy wyciagnac numer zapytania z naglowka pliku
                    try:
                        _, msisdn_dane = info["parse"](zestaw["nazwiska"], verbose=False)
                    except Exception:
                        msisdn_dane = None
                    if not msisdn_dane and dane_mapa:
                        msisdn_dane = next(iter(dane_mapa))
                if not msisdn_dane:
                    print(f"[!] {operator}/{etykieta}: same dane abonenckie, brak numeru — pominięto.")
                    continue
                df = pd.DataFrame(columns=[
                    "data", "czas", "czas_trwania", "typ", "strona_a", "bts_a", "imei_a",
                    "imsi_a", "strona_b", "bts_b", "imei_b", "imsi_b"])
                numer = klucz_numer(msisdn_dane)
                rekordy.append({
                    "operator": operator, "abonent": etykieta, "numer": numer,
                    "identyfikator": (dane_mapa.get(numer, {}) or {}).get("pesel", ""),
                    "folder": folder, "df": df, "nazwiska_map": dane_mapa,
                    "historia": dane_hist, "bts_map": {},
                    "okres_od": "", "okres_do": "",
                })
                print(f"    -> [same dane abonenckie] numer: {numer} | wpisow: {len(dane_mapa)}")
                continue

            ramki_df = []
            msisdn = None
            if zestaw.get("wykaz"):
                try:
                    df, msisdn = info["parse"](zestaw["wykaz"], verbose=False)
                    ramki_df.append(df)
                except BrakParsaraError as e:
                    print(f"[!] {e}")
                    continue
                except Exception as e:
                    print(f"[!] {operator}/{etykieta}: blad parsowania: {e}")
                    continue

            if zestaw.get("transmisja") and info.get("parse"):
                try:
                    df_tr, ms_tr = info["parse"](zestaw["transmisja"], verbose=False)
                    msisdn = msisdn or ms_tr
                    if df_tr is not None and not df_tr.empty:
                        df_tr = df_tr.copy()
                        df_tr["typ"] = "DATA"
                        ramki_df.append(df_tr)
                except Exception:
                    pass

            df = pd.concat(ramki_df, ignore_index=True) if ramki_df else pd.DataFrame()
            if df.empty and not msisdn:
                print(f"[!] {operator}/{etykieta}: brak danych i brak numeru w naglowku — pominięto.")
                continue
            if df.empty:
                df = pd.DataFrame(columns=[
                    "data", "czas", "czas_trwania", "typ", "strona_a", "bts_a", "imei_a",
                    "imsi_a", "strona_b", "bts_b", "imei_b", "imsi_b"])

            numer = klucz_numer(msisdn) if msisdn else wykryj_numer_abonenta(df, None, zestaw.get("token") or etykieta)
            nazwiska_map, historia = {}, {}
            if zestaw.get("nazwiska") and info.get("parse_nazwiska"):
                try:
                    nazwiska_map, historia = info["parse_nazwiska"](zestaw["nazwiska"], verbose=False)
                except Exception as e:
                    print(f"    [!] blad parsowania danych abonenckich: {e}")
            bts_map = {}
            if zestaw.get("bts") and info.get("parse_bts"):
                try:
                    bts_map = info["parse_bts"](zestaw["bts"], verbose=False)
                except Exception as e:
                    print(f"    [!] blad parsowania BTS: {e}")

            od, do = okres_bilingow(df)
            if len(zestawy) > 1 and numer:
                etykieta = f"{abonent} ({numer})"
            df = df.copy()
            df["abonent"] = etykieta
            df["operator"] = operator
            df["a_key"] = df["strona_a"].map(klucz_numer)
            df["b_key"] = df["strona_b"].map(klucz_numer)
            ramki.append(df)

            # KLUCZE IDENTYFIKACYJNE: 1) MSISDN (numer), 2) PESEL lub NIP/KRS.
            # Imie/nazwa NIGDY nie sa kluczem (moga byc bledne/falszywe) — tylko wyswietlanie.
            wpis_ab = nazwiska_map.get(numer) or (historia.get(numer, [{}])[-1] if historia.get(numer) else {}) or {}
            identyfikator = (wpis_ab.get("pesel") or wpis_ab.get("nip") or
                             wpis_ab.get("regon") or wpis_ab.get("krs") or "")

            rekordy.append({
                "operator": operator, "abonent": etykieta, "numer": numer,
                "identyfikator": identyfikator,
                "folder": folder, "df": df, "nazwiska_map": nazwiska_map,
                "historia": historia, "bts_map": bts_map,
                "okres_od": od, "okres_do": do,
            })
            print(f"    -> numer: {numer} | rekordow: {len(df)} | okres: {od} - {do}")

    # SCALANIE po kluczu MSISDN — ten sam numer moze wystapic w wielu zestawach
    # (rozne zapytania/systemy). Imie/nazwa nie jest kluczem i moze sie roznic.
    scalone = {}
    kolejnosc = []
    for r in rekordy:
        k = r["numer"] or f"_bez_numeru_{len(kolejnosc)}"
        if k not in scalone:
            r2 = dict(r)
            r2["df"] = r["df"]
            r2["nazwiska_map"] = dict(r["nazwiska_map"])
            r2["historia"] = {n: list(w) for n, w in r["historia"].items()}
            r2["bts_map"] = dict(r["bts_map"])
            r2["zrodla"] = [r["abonent"]]
            scalone[k] = r2
            kolejnosc.append(k)
        else:
            r2 = scalone[k]
            if not r["df"].empty:
                if r2["df"].empty:
                    r2["df"] = r["df"]
                else:
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
            r2["zrodla"].append(r["abonent"])
    for k in kolejnosc:
        r2 = scalone[k]
        if len(r2["zrodla"]) > 1:
            r2["abonent"] = r2["zrodla"][0]
            print(f"    [scalono] {r2['numer']}: {len(r2['zrodla'])} zrodel -> {r2['abonent']}")
    rekordy = [scalone[k] for k in kolejnosc]
    for r in rekordy:
        if not r["df"].empty:
            r["okres_od"], r["okres_do"] = okres_bilingow(r["df"])

    _ramki = [r["df"] for r in rekordy if not r["df"].empty]
    global_df = pd.concat(_ramki, ignore_index=True) if _ramki else pd.DataFrame()
    return rekordy, global_df


# ══════════════════════════════════════════════════════════════════════
# ANALIZA KRZYZOWA
# ══════════════════════════════════════════════════════════════════════

def komunikacja_bezposrednia(rekordy):
    """
    Laczy abonentow ze soba: zdarzenie, w ktorym strona A nalezy do abonenta X
    a strona B do abonenta Y (lub odwrotnie).
    Zwraca wiersze per (abonent, drugi abonent) ze statystykami kierunkow,
    tak jak wspolne_kontakty().
    """
    wiersze = []
    for rx in rekordy:
        nx = rx["numer"]
        if not nx:
            continue
        dfx = rx["df"]
        if dfx.empty:
            continue
        for ry in rekordy:
            ny = ry["numer"]
            if not ny or klucz_numer(nx) == klucz_numer(ny):
                continue
            mask_ab = (dfx["a_key"] == nx) & (dfx["b_key"] == ny)
            mask_ba = (dfx["a_key"] == ny) & (dfx["b_key"] == nx)
            sub = dfx[mask_ab | mask_ba]
            if sub.empty:
                continue
            voice = sub[sub["typ"] == "VOICE"]
            proba = sub[sub["typ"] == "PRÓBA"]
            sms = sub[sub["typ"].isin(["SMS", "MMS"])]
            dane = sub[sub["typ"] == "DATA"]
            ix, iy = rx.get("identyfikator", ""), ry.get("identyfikator", "")
            wiersze.append({
                "numer_kontaktu": ny,        # drugi abonent
                "nazwa_kontaktu": "",         # numery nie maja nazw w tym kontekscie
                "abonent": nx,
                "razem": len(sub),
                "voice_przych": int((voice["b_key"] == nx).sum()),
                "voice_wych": int((voice["a_key"] == nx).sum()),
                "proby_przych": int((proba["b_key"] == nx).sum()),
                "proby_wych": int((proba["a_key"] == nx).sum()),
                "sms_przych": int((sms["b_key"] == nx).sum()),
                "sms_wych": int((sms["a_key"] == nx).sum()),
                "dane": int(len(dane)),
                "okres_od": sub["data"].min(),
                "okres_do": sub["data"].max(),
                "ta_sama_osoba": "TAK" if (ix and iy and ix == iy) else "",
            })
    if not wiersze:
        return pd.DataFrame()
    kol = ["numer_kontaktu", "nazwa_kontaktu", "abonent", "razem",
           "voice_przych", "voice_wych", "proby_przych", "proby_wych",
           "sms_przych", "sms_wych", "dane", "okres_od", "okres_do", "ta_sama_osoba"]
    return pd.DataFrame(wiersze)[kol]

def wspolne_kontakty(rekordy):
    """
    Osoby trzecie (numery spoza zbioru abonentow) kontaktujace sie
    z co najmniej dwoma analizowanymi abonentami — Z ROZBITIEM per abonent:
    okres, liczby przych/wych/proby/SMS/MMS/DATA.
    Jesli nazwa kontaktu jest znana (z danych abonenckich badanych numerow), dolaczana.
    """
    zbior_numerow = {r["numer"] for r in rekordy if r["numer"]}
    mapa_nazw = {}
    for r in rekordy:
        mapa_nazw.update(r["nazwiska_map"])

    # kontakt -> {abonent_label: {stats}}
    per_kontakt = {}

    def statystyki(sub, numer):
        voice = sub[sub["typ"] == "VOICE"]
        proba = sub[sub["typ"] == "PRÓBA"]
        sms = sub[sub["typ"].isin(["SMS", "MMS"])]
        dane = sub[sub["typ"] == "DATA"]
        return {
            "razem": len(sub),
            "voice_wych": int((voice["a_key"] == numer).sum()),
            "voice_przych": int((voice["b_key"] == numer).sum()),
            "proby_wych": int((proba["a_key"] == numer).sum()),
            "proby_przych": int((proba["b_key"] == numer).sum()),
            "sms_wych": int((sms["a_key"] == numer).sum()),
            "sms_przych": int((sms["b_key"] == numer).sum()),
            "dane": int(len(dane)),
            "okres_od": sub["data"].min(),
            "okres_do": sub["data"].max(),
        }

    for r in rekordy:
        numer = r["numer"]
        if not numer:
            continue
        label_ab = numer  # w raporcie krzyzowym: TYLKO numer telefonu
        df = r["df"]
        if df.empty:
            continue
        mask_ab = (df["a_key"] == numer) | (df["b_key"] == numer)
        sub = df[mask_ab]
        if sub.empty:
            continue
        druga = sub.apply(
            lambda w: w["b_key"] if w["a_key"] == numer else w["a_key"], axis=1)
        for num_kontaktu in druga.unique():
            if not num_kontaktu or num_kontaktu in zbior_numerow:
                continue
            ev = sub[druga == num_kontaktu]
            per_kontakt.setdefault(num_kontaktu, {})[label_ab] = statystyki(ev, numer)

    wiersze = []
    for num, per_ab in per_kontakt.items():
        if len(per_ab) < 2:
            continue
        dane_kont = mapa_nazw.get(num, {})
        nazwa = dane_kont.get("nazwa", "")
        for label_ab, st in per_ab.items():
            wiersze.append({
                "numer_kontaktu": num,
                "nazwa_kontaktu": nazwa,
                "abonent": label_ab,
                **st,
            })
    if not wiersze:
        return pd.DataFrame()
    kol = ["numer_kontaktu", "nazwa_kontaktu", "abonent", "razem",
           "voice_przych", "voice_wych", "proby_przych", "proby_wych",
           "sms_przych", "sms_wych", "dane", "okres_od", "okres_do"]
    out = pd.DataFrame(wiersze)[kol]
    out = out.sort_values(["numer_kontaktu", "abonent"]).reset_index(drop=True)
    return out


def wspolne_imei(rekordy):
    """
    IMEI wystepujace w billingach co najmniej dwoch roznych abonentow
    (mozliwe wspoluzytkowanie/wymiana urzadzen).
    """
    per_imei = {}
    for r in rekordy:
        df = r["df"]
        imeis = pd.concat([df["imei_a"], df["imei_b"]])
        imeis = imeis[~imeis.isin(NIE_IMEI) & imeis.notna()].unique()
        for imei in imeis:
            per_imei.setdefault(imei, set()).add(f'{r["abonent"]} [{r["numer"]}]')
    wiersze = [
        {"imei": imei, "abonenci": " | ".join(sorted(ab)), "liczba_abonentow": len(ab)}
        for imei, ab in per_imei.items() if len(ab) >= 2
    ]
    if not wiersze:
        return pd.DataFrame()
    return pd.DataFrame(wiersze).sort_values("liczba_abonentow", ascending=False).reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════
# RAPORT ZBIORCZY (TXT + CSV)
# ══════════════════════════════════════════════════════════════════════

def generuj_raport_zbiorczy(rekordy, bezposrednia, wspolne, imei_df, out_txt, out_csv):
    L = []
    L.append("=" * 120)
    L.append("  RAPORT ZBIORCZY — ANALIZA KRZYZOWA BILINGOW")
    L.append(f"  Wygenerowano: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    L.append(f"  Abonentow: {len(rekordy)}")
    L.append("=" * 120)
    L.append("")

    # liczniki zdarzen KRZYZOWYCH per abonent (nie suma calego billingu)
    dir_cnt, sha_cnt = {}, {}
    if not bezposrednia.empty:
        for _, rr in bezposrednia.iterrows():
            dir_cnt[rr["abonent"]] = dir_cnt.get(rr["abonent"], 0) + int(rr["razem"])
    if not wspolne.empty:
        for _, rr in wspolne.iterrows():
            sha_cnt[rr["abonent"]] = sha_cnt.get(rr["abonent"], 0) + int(rr["razem"])

    # SEKCJA A — abonenci
    L.append("-" * 130)
    L.append("  SEKCJA A: ANALIZOWANI ABONENCI — liczniki zdarzen KRZYZOWYCH")
    L.append("-" * 130)
    L.append("  {:>3} {:<28} {:<14} {:<18} {:<10} {:<12} {:<12} {:>8} {:>10}".format(
        "Lp", "Folder abonenta", "Numer (MSISDN)", "PESEL/NIP-KRS", "Operator",
        "Okres od", "Okres do", "Z innymi", "Z kontakt."))
    L.append("-" * 130)
    for i, r in enumerate(rekordy, 1):
        num = r["numer"]
        L.append("  {:>3} {:<28} {:<14} {:<18} {:<10} {:<12} {:<12} {:>8} {:>10}".format(
            i, r["abonent"][:28], num or "-", r.get("identyfikator", "")[:18],
            r["operator"], r["okres_od"], r["okres_do"],
            dir_cnt.get(num, 0), sha_cnt.get(num, 0)))
    L.append("")
    L.append("  'Z innymi'   = zdarzenia z innymi ANALIZOWANYMI abonentami (sekcja B)")
    L.append("  'Z kontakt.' = zdarzenia ze wspolnymi kontaktami osob trzecich (sekcja C)")
    L.append("")

    # SEKCJA B — bezposrednia
    L.append("-" * 110)
    L.append("  SEKCJA B: KOMUNIKACJA BEZPOSREDNIA MIEDZY ANALIZOWANYMI ABONENTAMI")
    L.append("-" * 110)
    if not bezposrednia.empty:
        akt_num = None
        lp = 0
        for _, r in bezposrednia.iterrows():
            klucz_pary = tuple(sorted([str(r["abonent"]), str(r["numer_kontaktu"])]))
            if klucz_pary != akt_num:
                akt_num = klucz_pary
                lp += 1
                n_ab = 0
                oso = ""
                for _, rr in bezposrednia.iterrows():
                    if tuple(sorted([str(rr["abonent"]), str(rr["numer_kontaktu"])])) == klucz_pary:
                        n_ab += 1
                        if rr.get("ta_sama_osoba"):
                            oso = "  [TA SAMA OSOBA/FIRMA]"
                L.append("")
                L.append(f"  #{lp} POLACZENIE BEZPOSREDNIE: {klucz_pary[0]} <-> {klucz_pary[1]}{oso}")
                L.append("  " + "-" * 126)
                L.append("  {:<14} {:<14} {:<23} {:>9} {:>4} {:>4} {:>4} {:>4} {:>4} {:>4} {:>4} {:>5}".format(
                    "Numer", "Drugi numer", "Okres", "Razem", "Vprz", "Vwych", "Pprz", "Pwych",
                    "Sprz", "Swych", "DATA", ""))
            L.append("  {:<14} {:<14} {:<23} {:>9} {:>4} {:>4} {:>4} {:>4} {:>4} {:>4} {:>4} {:>5}".format(
                str(r["abonent"])[:14], str(r["numer_kontaktu"])[:14],
                f'{r["okres_od"]} - {r["okres_do"]}'[:23],
                r["razem"], r["voice_przych"], r["voice_wych"],
                r["proby_przych"], r["proby_wych"], r["sms_przych"], r["sms_wych"],
                r["dane"], ""))
        L.append("")
        L.append("  Legenda: Vprz/Vwych - polaczenia przychodzace/wychodzace, "
                 "Pprz/Pwych - proby, Sprz/Swych - SMS/MMS, DATA - transmisje danych.")
    else:
        L.append("  Brak bezposredniej komunikacji miedzy analizowanymi abonentami.")
    L.append("")

    # SEKCJA C — wspolne kontakty (z rozbiciem per abonent)
    L.append("-" * 130)
    L.append("  SEKCJA C: OSOBY TRZECIE LACZACE ABONENTOW (wspolne kontakty) — szczegoly")
    L.append("-" * 130)
    if not wspolne.empty:
        akt_num = None
        lp = 0
        for _, r in wspolne.iterrows():
            if r["numer_kontaktu"] != akt_num:
                akt_num = r["numer_kontaktu"]
                lp += 1
                nazwa = f"  ({r['nazwa_kontaktu']})" if r["nazwa_kontaktu"] else ""
                n_ab = int((wspolne["numer_kontaktu"] == akt_num).sum())
                L.append("")
                L.append(f"  #{lp} WSPOLNY KONTAKT: {akt_num}{nazwa} — laczy {n_ab} abonentow")
                L.append("  " + "-" * 126)
                L.append("  {:<14} {:<23} {:>9} {:>4} {:>4} {:>4} {:>4} {:>4} {:>4} {:>4} {:>5}".format(
                    "Numer abonenta", "Okres", "Zd.z kont.", "Vprz", "Vwych", "Pprz", "Pwych",
                    "Sprz", "Swych", "DATA", ""))
            L.append("  {:<14} {:<23} {:>9} {:>4} {:>4} {:>4} {:>4} {:>4} {:>4} {:>4} {:>5}".format(
                str(r["abonent"])[:14],
                f'{r["okres_od"]} - {r["okres_do"]}'[:23],
                r["razem"], r["voice_przych"], r["voice_wych"],
                r["proby_przych"], r["proby_wych"], r["sms_przych"], r["sms_wych"],
                r["dane"], ""))
        L.append("")
        L.append("  Legenda: Zd.z kont. = WSZYSTKIE zdarzenia abonenta z TYM kontaktem (nie caly billing);")
        L.append("  Vprz/Vwych - polaczenia przychodzace/wychodzace, Pprz/Pwych - proby,")
        L.append("  Sprz/Swych - SMS/MMS, DATA - transmisje danych.")
    else:
        L.append("  Brak wspolnych kontaktow osob trzecich.")
    L.append("")

    # SEKCJA D — wspolne IMEI
    L.append("-" * 110)
    L.append("  SEKCJA D: URZADZENIA (IMEI) WSPOLNE DLA WIECEJ NIZ JEDNEGO ABONENTA")
    L.append("-" * 110)
    if not imei_df.empty:
        L.append("  {:>3} {:<18} {:>3}  {:<70}".format("Lp", "IMEI", "Ab.", "Abonenci"))
        L.append("-" * 110)
        for i, (_, r) in enumerate(imei_df.iterrows(), 1):
            L.append("  {:>3} {:<18} {:>3}  {:<70}".format(
                i, r["imei"], r["liczba_abonentow"], r["abonenci"][:70]))
    else:
        L.append("  Brak wspolnych urzadzen.")
    L.append("")
    L.append("=" * 120)
    L.append("  KONIEC RAPORTU ZBIORCZEGO")
    L.append("=" * 120)

    with open(out_txt, "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    # CSV
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["ANALIZA KRZYZOWA BILINGOW"])
        w.writerow([])
        w.writerow(["ABONENCI — liczniki zdarzen KRZYZOWYCH"])
        w.writerow(["Folder", "Numer (MSISDN)", "PESEL/NIP-KRS", "Operator", "Okres od", "Okres do",
                    "Zdarzen z innymi abonentami", "Zdarzen ze wspolnymi kontaktami"])
        for r in rekordy:
            num = r["numer"]
            w.writerow([r["abonent"], num, r.get("identyfikator", ""), r["operator"],
                        r["okres_od"], r["okres_do"],
                        dir_cnt.get(num, 0), sha_cnt.get(num, 0)])
        w.writerow([])
        w.writerow(["KOMUNIKACJA BEZPOSREDNIA — szczegoly per abonent"])
        w.writerow(["Numer abonenta", "Numer drugiego abonenta",
                    "Razem zdarzen", "Voice przych", "Voice wych",
                    "Proby przych", "Proby wych", "SMS przych", "SMS wych", "DATA",
                    "Okres od", "Okres do", "Ta sama osoba/firma"])
        if not bezposrednia.empty:
            for _, r in bezposrednia.iterrows():
                w.writerow([r["abonent"], r["numer_kontaktu"],
                            r["razem"], r["voice_przych"], r["voice_wych"],
                            r["proby_przych"], r["proby_wych"], r["sms_przych"], r["sms_wych"],
                            r["dane"], r["okres_od"], r["okres_do"], r.get("ta_sama_osoba", "")])
        w.writerow([])
        w.writerow(["WSPOLNE KONTAKTY OSOB TRZECICH — szczegoly per abonent"])
        w.writerow(["Numer kontaktu", "Nazwa kontaktu", "Numer abonenta",
                    "Zdarzen z kontaktem", "Voice przych", "Voice wych",
                    "Proby przych", "Proby wych", "SMS przych", "SMS wych", "DATA",
                    "Okres od", "Okres do"])
        if not wspolne.empty:
            for _, r in wspolne.iterrows():
                w.writerow([r["numer_kontaktu"], r["nazwa_kontaktu"], r["abonent"],
                            r["razem"], r["voice_przych"], r["voice_wych"],
                            r["proby_przych"], r["proby_wych"], r["sms_przych"], r["sms_wych"],
                            r["dane"], r["okres_od"], r["okres_do"]])
        w.writerow([])
        w.writerow(["WSPOLNE IMEI"])
        w.writerow(["IMEI", "Liczba abonentow", "Abonenci"])
        if not imei_df.empty:
            for _, r in imei_df.iterrows():
                w.writerow([r["imei"], r["liczba_abonentow"], r["abonenci"]])


# ══════════════════════════════════════════════════════════════════════
# RAPORTY PER NUMER (klasyczne, z analizaBilling)
# ══════════════════════════════════════════════════════════════════════

def raport_per_numer(r, outdir):
    """Generuje klasyczny raport dla jednego abonenta (bez wypisywania na ekran)."""
    target = r["numer"]
    if not target:
        print(f"[!] {r['abonent']}: brak numeru — pominięto raport per numer.")
        return
    df = r["df"]
    nazwiska_map, historia = r["nazwiska_map"], r["historia"]
    bts_map = r["bts_map"]
    abonent_info = dane_abonenta(target, nazwiska_map)
    od, do = r["okres_od"], r["okres_do"]

    kp = ab.kontakty_zdarzenia(df, target, nazwiska_map)
    ks = ab.kontakty_sms(df, target, nazwiska_map)
    bts = ab.bts_polaczone(df, target, bts_map)
    imei_df = ab.imei_dla_numeru(df, target)
    imsi_df = ab.imsi_dla_numeru(df, target)
    inet = ab.internet_stats(df, target)

    from common import dedup_historia
    historia_ab = {target: dedup_historia(historia[target])} if target in historia else None
    hk = {}
    for num in pd.concat([kp["numer_kontaktu"], ks["numer_kontaktu"]]).unique():
        n = klucz_numer(num)
        if n in historia and len(historia[n]) > 1:
            hk[n] = dedup_historia(historia[n])

    target_dir = os.path.join(outdir, target)
    os.makedirs(target_dir, exist_ok=True)
    p_txt = os.path.join(target_dir, f"{target}_RAPORT_KONCOWY.txt")
    p_csv = os.path.join(target_dir, f"{target}_RAPORT_KONCOWY.csv")
    with open(p_txt, "w", encoding="utf-8") as f:
        f.write(ab.generuj_raport_txt(target, kp, ks, bts, imei_df, abonent_info, inet, od, do,
                                      historia_ab, hk, bloki=None, imsi_df=imsi_df))
    ab.generuj_raport_csv(target, kp, ks, bts, imei_df, abonent_info, inet, od, do, p_csv,
                          historia_ab, hk, bloki=None, imsi_df=imsi_df)
    p_docx = os.path.join(target_dir, f"{target}_RAPORT_KONCOWY.docx")
    ab.generuj_raport_docx(target, kp, ks, bts, imei_df, abonent_info, inet, od, do, p_docx,
                           historia_ab, hk, bloki=None, imsi_df=imsi_df)
    print(f"    raport: {p_txt}")


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def przebieg(root: str, outdir: str = None, bez_per_numer: bool = False):
    """Pelny przebieg analizy krzyzowej (wywolywany z CLI i z analizaBilling).
    outdir=None -> output/RRRR-MM-DD_GGMM (folder wynikowy nazwany data + godzina)."""
    if not outdir:
        from datetime import datetime
        outdir = os.path.join("./output", datetime.now().strftime("%Y-%m-%d_%H%M"))
    if not os.path.isdir(root):
        print(f"[!] Nie ma takiego katalogu: {root}")
        sys.exit(1)

    rekordy, global_df = wczytaj_wszystkie(root)
    if not rekordy:
        print("[!] Nie wczytano zadnych danych.")
        sys.exit(1)

    os.makedirs(outdir, exist_ok=True)
    krzyz_dir = os.path.join(outdir, "krzyzowy")
    os.makedirs(krzyz_dir, exist_ok=True)

    if not bez_per_numer:
        print("\n[+] Raporty per numer:")
        for r in rekordy:
            try:
                raport_per_numer(r, outdir)
            except Exception as e:
                print(f"    [!] {r['abonent']}: blad raportu: {e}")

    bezposrednia = komunikacja_bezposrednia(rekordy)
    wspolne = wspolne_kontakty(rekordy)
    imei_df = wspolne_imei(rekordy)

    out_txt = os.path.join(krzyz_dir, "RAPORT_ZBIORCZY_KRZYZOWY.txt")
    out_csv = os.path.join(krzyz_dir, "RAPORT_ZBIORCZY_KRZYZOWY.csv")
    generuj_raport_zbiorczy(rekordy, bezposrednia, wspolne, imei_df, out_txt, out_csv)

    print("\n" + "=" * 100)
    print("  PODSUMOWANIE ANALIZY KRZYZOWEJ")
    print("=" * 100)
    print(f"  Abonentow: {len(rekordy)}")
    print(f"  Bezposrednich polaczen miedzy abonentami: {len(bezposrednia)} kierunkow")
    n_wspolnych = wspolne["numer_kontaktu"].nunique() if not wspolne.empty else 0
    print(f"  Wspolnych kontaktow osob trzecich: {n_wspolnych} numerow ({len(wspolne)} powiazan)")
    print(f"  Wspolnych urzadzen (IMEI): {len(imei_df)}")
    print("=" * 100)
    print(f"\n[+] RAPORTY PER NUMER:   {os.path.abspath(outdir)}")
    print(f"[+] RAPORT ZBIORCZY TXT: {os.path.abspath(out_txt)}")
    print(f"[+] RAPORT ZBIORCZY CSV: {os.path.abspath(out_csv)}")


def main():
    ap = argparse.ArgumentParser(description="Analiza krzyzowa bilingow (multi-operator)")
    ap.add_argument("--dane", default="./input", help="katalog glowny ze struktura <operator>/<abonent>/ (domyslnie: ./input)")
    ap.add_argument("--outdir", default="./raport_krzyzowy")
    ap.add_argument("--bez-per-numer", action="store_true", help="pomin klasyczne raporty per numer")
    args = ap.parse_args()
    przebieg(args.dane, args.outdir, args.bez_per_numer)


if __name__ == "__main__":
    main()
