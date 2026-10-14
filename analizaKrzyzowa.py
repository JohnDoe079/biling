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

Uwaga: glownym entry pointem jest analizaBilling.py (raporty per numer +
automatyczna analiza krzyzowa). Ten modul dostarcza funkcje analizy
krzyzowej i generator raportu zbiorczego; rekordy z polem tryb="imei"
(dane kluczowane po urzadzeniu) sa pomijane w sekcjach B i C, ale ich
IMEI uczestnicza w sekcji D (wspolne urzadzenia).
"""
import argparse
import csv
import itertools
import os
import sys
from datetime import datetime

import pandas as pd

from common import (
    skanuj_dane, klucz_numer, normalizuj_numer, format_numer, fmt_czas, input_path,
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

            if not zestaw.get("wykaz") and not zestaw.get("transmisja"):
                print(f"[!] {operator}/{etykieta}: brak plikow z danymi — pominięto.")
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

    global_df = pd.concat([r["df"] for r in rekordy], ignore_index=True) if rekordy else pd.DataFrame()
    return rekordy, global_df


# ══════════════════════════════════════════════════════════════════════
# ANALIZA KRZYZOWA
# ══════════════════════════════════════════════════════════════════════

def komunikacja_bezposrednia(rekordy):
    """
    Laczy abonentow ze soba: zdarzenie, w ktorym strona A nalezy do abonenta X
    a strona B do abonenta Y (lub odwrotnie). Zwraca DataFrame par.
    Rekordy tryb="imei" (dane urzadzenia) sa pomijane — nie sa numerami MSISDN.
    """
    wiersze = []
    for rx, ry in itertools.permutations(rekordy, 2):
        nx, ny = rx["numer"], ry["numer"]
        if (not nx or not ny or nx == ny
                or rx.get("tryb") == "imei" or ry.get("tryb") == "imei"):
            continue
        dfx = rx["df"]
        # zdarzenia gdzie abonent X to strona A a numer abonenta Y to strona B
        mask_ab = (dfx["a_key"] == nx) & (dfx["b_key"] == ny)
        mask_ba = (dfx["a_key"] == ny) & (dfx["b_key"] == nx)
        sub = dfx[mask_ab | mask_ba]
        if sub.empty:
            continue
        voice = sub[sub["typ"] == "VOICE"]
        proba = sub[sub["typ"] == "PRÓBA"]
        sms = sub[sub["typ"].isin(["SMS", "MMS"])]
        ix, iy = rx.get("identyfikator", ""), ry.get("identyfikator", "")
        # Dane abonenckie z folderow danych abonentow (operator podaje dane
        # tylko ze swojej sieci — dla numeru z innej sieci bierzemy z jego zrodla).
        dane_od = ab.dane_abonenta(nx, rx["nazwiska_map"]).get("nazwa") or ix
        dane_do = ab.dane_abonenta(ny, ry["nazwiska_map"]).get("nazwa") or iy
        wiersze.append({
            "od": rx["abonent"], "numer_od": nx, "operator_od": rx["operator"],
            "id_od": ix, "dane_od": dane_od,
            "do": ry["abonent"], "numer_do": ny, "operator_do": ry["operator"],
            "id_do": iy, "dane_do": dane_do,
            "ta_sama_osoba": "TAK" if (ix and iy and ix == iy) else "",
            "voice": len(voice), "proby": len(proba), "sms_mms": len(sms),
            "razem": len(sub),
            "zakres_od": sub["data"].min(), "zakres_do": sub["data"].max(),
        })
    if not wiersze:
        return pd.DataFrame()
    out = pd.DataFrame(wiersze)
    return out.sort_values("razem", ascending=False).reset_index(drop=True)


def wspolne_kontakty(rekordy):
    """
    Osoby trzecie (numery spoza zbioru abonentow) kontaktujace sie
    z co najmniej dwoma analizowanymi abonentami.
    Zwraca DataFrame: numer_osoby, abonenci, operatorzy, liczby zdarzen per abonent.
    """
    zbior_numerow = {r["numer"] for r in rekordy
                     if r["numer"] and r.get("tryb") != "imei"}
    kontakty = {}  # klucz_numer -> {abonent_key: liczba}
    for r in rekordy:
        if r.get("tryb") == "imei" or not r["numer"]:
            continue
        df = r["df"]
        ident = r.get("identyfikator", "")
        klucz_ab = f'{r["abonent"]} [{r["numer"]}]' + (f' {{{ident}}}' if ident else '')
        sub = df[(df["a_key"] == r["numer"]) | (df["b_key"] == r["numer"])]
        druga = sub.apply(lambda w: w["b_key"] if w["a_key"] == r["numer"] else w["a_key"], axis=1)
        for num in druga:
            if not num or num in zbior_numerow:
                continue
            kontakty.setdefault(num, {})
            kontakty[num][klucz_ab] = kontakty[num].get(klucz_ab, 0) + 1

    wiersze = []
    for num, per_ab in kontakty.items():
        if len(per_ab) < 2:
            continue
        wiersze.append({
            "numer_kontaktu": num,
            "abonenci": " | ".join(sorted(per_ab.keys())),
            "liczba_abonentow": len(per_ab),
            "razem_zdarzen": sum(per_ab.values()),
        })
    if not wiersze:
        return pd.DataFrame()
    return pd.DataFrame(wiersze).sort_values(
        ["liczba_abonentow", "razem_zdarzen"], ascending=False).reset_index(drop=True)


def wspolne_imei(rekordy):
    """
    IMEI wystepujace w billingach co najmniej dwoch roznych abonentow
    (mozliwe wspoluzytkowanie/wymiana urzadzen). Uwzględnia takze zestawy
    kluczowane po IMEI (tryb="imei").
    """
    per_imei = {}
    for r in rekordy:
        df = r["df"]
        imeis = pd.concat([df["imei_a"], df["imei_b"]])
        imeis = imeis[~imeis.isin(NIE_IMEI) & imeis.notna()].unique()
        for imei in imeis:
            per_imei.setdefault(imei, set()).add(f'{r["abonent"]} [{r["numer"] or r.get("cel") or "IMEI"}]')
    wiersze = [
        {"imei": imei, "abonenci": " | ".join(sorted(ab)), "liczba_abonentow": len(ab)}
        for imei, ab in per_imei.items() if len(ab) >= 2
    ]
    if not wiersze:
        return pd.DataFrame()
    return pd.DataFrame(wiersze).sort_values("liczba_abonentow", ascending=False).reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════
# GRUPOWANIE OSOB / FIRM (klucz wtorny: PESEL / NIP-KRS)
# ══════════════════════════════════════════════════════════════════════
# Operator podaje dane abonenckie tylko ze swojej sieci — klucz wtorny
# (PESEL osoby / NIP-KRS firmy) laczy numery roznych operatorow w jedna
# osobe. Bez identyfikatora osoba = pojedynczy numer.

def osoby_z_rekordow(rekordy):
    """Zwraca {klucz_osoby: {...}} — osoby/firmy z numerami, IMEI, zdarzeniami."""
    osoby = {}
    for r in rekordy:
        if r.get("tryb") == "imei" or not r["numer"]:
            continue
        klucz = r.get("identyfikator") or f"MSISDN:{r['numer']}"
        o = osoby.setdefault(klucz, {
            "klucz": klucz, "numery": [], "operatory": set(),
            "zrodla": [], "nazwa": "", "imei": set(), "zdarzen": 0,
            "okres_od": "", "okres_do": "",
        })
        o["numery"].append(r["numer"])
        o["operatory"].add(r["operator"])
        o["zrodla"].append(r["abonent"])
        o["zdarzen"] += len(r["df"])
        if not o["nazwa"]:
            d = ab.dane_abonenta(r["numer"], r["nazwiska_map"])
            o["nazwa"] = d.get("nazwa", "")
        df = r["df"]
        if not df.empty:
            ka = df["a_key"] if "a_key" in df.columns else df["strona_a"].map(klucz_numer)
            kb = df["b_key"] if "b_key" in df.columns else df["strona_b"].map(klucz_numer)
            for kol_imei, maska in (("imei_a", ka == r["numer"]), ("imei_b", kb == r["numer"])):
                s = df[maska][kol_imei]
                s = s[~s.isin(NIE_IMEI) & s.notna()]
                o["imei"].update(s.unique())
            od, do = okres_bilingow(df)
            if od and (not o["okres_od"] or od < o["okres_od"]):
                o["okres_od"] = od
            if do and (not o["okres_do"] or do > o["okres_do"]):
                o["okres_do"] = do
    return osoby

def komunikacja_osob(bezposrednia, osoby):
    """Agregacja komunikacji bezposredniej z par numerow na pary OSOB."""
    numer2osoba = {}
    for klucz, o in osoby.items():
        for n in o["numery"]:
            numer2osoba[klucz_numer(n)] = klucz
    agg = {}
    if bezposrednia.empty:
        return pd.DataFrame()
    for _, r in bezposrednia.iterrows():
        ko = numer2osoba.get(klucz_numer(r["numer_od"]))
        kd = numer2osoba.get(klucz_numer(r["numer_do"]))
        if not ko or not kd:
            continue
        a = agg.setdefault((ko, kd), {"voice": 0, "proby": 0, "sms_mms": 0, "razem": 0,
                                      "zakres_od": None, "zakres_do": None})
        a["voice"] += r["voice"]; a["proby"] += r["proby"]
        a["sms_mms"] += r["sms_mms"]; a["razem"] += r["razem"]
        zo, zd = r["zakres_od"], r["zakres_do"]
        if zo and (a["zakres_od"] is None or zo < a["zakres_od"]):
            a["zakres_od"] = zo
        if zd and (a["zakres_do"] is None or zd > a["zakres_do"]):
            a["zakres_do"] = zd
    wiersze = []
    for (ko, kd), a in agg.items():
        wiersze.append({
            "od_osoba": osoby[ko]["nazwa"] or "(brak danych)",
            "od_klucz": ko, "do_osoba": osoby[kd]["nazwa"] or "(brak danych)",
            "do_klucz": kd,
            "ta_sama_osoba": "TAK" if ko == kd else "",
            **a,
        })
    if not wiersze:
        return pd.DataFrame()
    return pd.DataFrame(wiersze).sort_values("razem", ascending=False).reset_index(drop=True)


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

    # SEKCJA A — osoby/firmy (grupowanie po PESEL / NIP-KRS)
    osoby = osoby_z_rekordow(rekordy)
    L.append("-" * 110)
    L.append("  SEKCJA A: ANALIZOWANE OSOBY / FIRMY (grupowanie po PESEL / NIP-KRS)")
    L.append("-" * 110)
    L.append("  {:>3} {:<24} {:<13} {:<26} {:<18} {:<22} {:>8}".format(
        "Lp", "Nazwa / Firma", "PESEL/NIP-KRS", "Numery (MSISDN)", "Operatorzy",
        "Urzadzenia (IMEI)", "Zdarzen"))
    L.append("-" * 130)
    for i, (klucz, o) in enumerate(osoby.items(), 1):
        kl = klucz if not klucz.startswith("MSISDN:") else "-"
        L.append("  {:>3} {:<24} {:<13} {:<26} {:<18} {:<22} {:>8}".format(
            i, (o["nazwa"] or "(brak danych)")[:24], kl[:13],
            ", ".join(format_numer(n) for n in o["numery"])[:26],
            ", ".join(sorted(o["operatory"]))[:18],
            ", ".join(sorted(o["imei"]))[:22] if o["imei"] else "-",
            o["zdarzen"]))
    L.append("")

    # SEKCJA A2 — wykaz analizowanych numerow (szczegolowy)
    L.append("-" * 110)
    L.append("  SEKCJA A2: WYKAZ ANALIZOWANYCH NUMEROW (MSISDN)")
    L.append("-" * 110)
    L.append("  {:>3} {:<28} {:<14} {:<18} {:<10} {:<12} {:<12} {:>8}".format(
        "Lp", "Folder abonenta", "Numer (MSISDN)", "PESEL/NIP-KRS", "Operator",
        "Okres od", "Okres do", "Zdarzenia"))
    L.append("-" * 130)
    for i, r in enumerate(rekordy, 1):
        L.append("  {:>3} {:<28} {:<14} {:<18} {:<10} {:<12} {:<12} {:>8}".format(
            i, r["abonent"][:28], format_numer(r["numer"]) or "-", r.get("identyfikator", "")[:18],
            r["operator"], r["okres_od"], r["okres_do"], len(r["df"])))
    L.append("")

    # SEKCJA B — bezposrednia (agregacja do poziomu osob/firm)
    kom_osob = komunikacja_osob(bezposrednia, osoby)
    L.append("-" * 110)
    L.append("  SEKCJA B: KOMUNIKACJA MIEDZY OSOBAMI / FIRMAMI (agregacja po PESEL / NIP-KRS)")
    L.append("-" * 110)
    if not kom_osob.empty:
        L.append("  {:>3} {:<22} {:<13} {:<22} {:<13} {:<4} {:>6} {:>6} {:>8} {:>7} {:<19}".format(
            "Lp", "Osoba/Firma (od)", "PESEL/NIP od", "Osoba/Firma (do)", "PESEL/NIP do",
            "Oso.", "Voice", "Proby", "SMS/MMS", "Razem", "Zakres czasu"))
        L.append("-" * 150)
        for i, (_, r) in enumerate(kom_osob.iterrows(), 1):
            ko = r["od_klucz"] if not str(r["od_klucz"]).startswith("MSISDN:") else "-"
            kd = r["do_klucz"] if not str(r["do_klucz"]).startswith("MSISDN:") else "-"
            L.append("  {:>3} {:<22} {:<13} {:<22} {:<13} {:<4} {:>6} {:>6} {:>8} {:>7} {:<19}".format(
                i, r["od_osoba"][:22], str(ko)[:13], r["do_osoba"][:22], str(kd)[:13],
                r.get("ta_sama_osoba", ""), r["voice"], r["proby"], r["sms_mms"], r["razem"],
                f'{r["zakres_od"]} - {r["zakres_do"]}'))
    else:
        L.append("  Brak bezposredniej komunikacji miedzy analizowanymi osobami/firmami.")
    L.append("")

    # SEKCJA C — wspolne kontakty
    L.append("-" * 110)
    L.append("  SEKCJA C: OSOBY TRZECIE LACZACE ABONENTOW (wspolne kontakty)")
    L.append("-" * 110)
    if not wspolne.empty:
        L.append("  {:>3} {:<14} {:>3} {:>8}  {:<70}".format(
            "Lp", "Numer", "Ab.", "Zdarzen", "Abonenci laczeni tym numerem"))
        L.append("-" * 110)
        for i, (_, r) in enumerate(wspolne.iterrows(), 1):
            L.append("  {:>3} {:<14} {:>3} {:>8}  {:<70}".format(
                i, format_numer(r["numer_kontaktu"]), r["liczba_abonentow"], r["razem_zdarzen"],
                r["abonenci"][:70]))
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
        osoby = osoby_z_rekordow(rekordy)
        kom_osob = komunikacja_osob(bezposrednia, osoby)
        w.writerow(["OSOBY / FIRMY (grupowanie po PESEL / NIP-KRS)"])
        w.writerow(["Lp", "Nazwa / Firma", "PESEL/NIP-KRS", "Numery (MSISDN)", "Operatorzy",
                    "Urzadzenia (IMEI)", "Liczba zdarzen"])
        for i, (klucz, o) in enumerate(osoby.items(), 1):
            kl = klucz if not klucz.startswith("MSISDN:") else ""
            w.writerow([i, o["nazwa"] or "(brak danych)", kl,
                        " | ".join(format_numer(n) for n in o["numery"]),
                        " | ".join(sorted(o["operatory"])),
                        " | ".join(sorted(o["imei"])) if o["imei"] else "",
                        o["zdarzen"]])
        w.writerow([])
        w.writerow(["WYKAZ ANALIZOWANYCH NUMEROW (MSISDN)"])
        w.writerow(["Folder", "Numer (MSISDN)", "PESEL/NIP-KRS", "Operator", "Okres od", "Okres do", "Liczba zdarzen"])
        for r in rekordy:
            w.writerow([r["abonent"], format_numer(r["numer"]) if r["numer"] else "", r.get("identyfikator", ""), r["operator"],
                        r["okres_od"], r["okres_do"], len(r["df"])])
        w.writerow([])
        w.writerow(["KOMUNIKACJA MIEDZY OSOBAMI / FIRMAMI (agregacja po PESEL / NIP-KRS)"])
        w.writerow(["Osoba/Firma (od)", "PESEL/NIP od", "Osoba/Firma (do)", "PESEL/NIP do",
                    "Ta sama osoba/firma",
                    "Voice", "Proby", "SMS/MMS", "Razem", "Zakres od", "Zakres do"])
        if not kom_osob.empty:
            for _, r in kom_osob.iterrows():
                ko = r["od_klucz"] if not str(r["od_klucz"]).startswith("MSISDN:") else ""
                kd = r["do_klucz"] if not str(r["do_klucz"]).startswith("MSISDN:") else ""
                w.writerow([r["od_osoba"], ko, r["do_osoba"], kd,
                            r.get("ta_sama_osoba", ""),
                            r["voice"], r["proby"], r["sms_mms"], r["razem"],
                            r["zakres_od"], r["zakres_do"]])
        w.writerow([])
        w.writerow(["WSPOLNE KONTAKTY OSOB TRZECICH"])
        w.writerow(["Numer kontaktu", "Liczba abonentow", "Razem zdarzen", "Abonenci"])
        if not wspolne.empty:
            for _, r in wspolne.iterrows():
                w.writerow([format_numer(r["numer_kontaktu"]), r["liczba_abonentow"], r["razem_zdarzen"], r["abonenci"]])
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
    """Generuje klasyczny raport dla jednego abonenta (bez wypisywania na ekran).
    Pomija rekordy tryb="imei" (dane urzadzenia — raportuje je analizaBilling)."""
    target = r["numer"]
    if not target or r.get("tryb") == "imei":
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
    inet = ab.internet_stats(df, target)

    historia_ab = {target: historia[target]} if target in historia else None
    hk = {}
    for num in pd.concat([kp["numer_kontaktu"], ks["numer_kontaktu"]]).unique():
        n = klucz_numer(num)
        if n in historia and len(historia[n]) > 1:
            hk[n] = historia[n]

    target_dir = os.path.join(outdir, target)
    os.makedirs(target_dir, exist_ok=True)
    p_txt = os.path.join(target_dir, f"{target}_RAPORT_KONCOWY.txt")
    p_csv = os.path.join(target_dir, f"{target}_RAPORT_KONCOWY.csv")
    with open(p_txt, "w", encoding="utf-8") as f:
        f.write(ab.generuj_raport_txt(target, kp, ks, bts, imei_df, abonent_info, inet, od, do,
                                      historia_ab, hk, bloki=None))
    ab.generuj_raport_csv(target, kp, ks, bts, imei_df, abonent_info, inet, od, do, p_csv,
                          historia_ab, hk, bloki=None)
    print(f"    raport: {p_txt}")


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def przebieg(root: str, outdir: str, bez_per_numer: bool = False):
    """Pelny przebieg analizy krzyzowej (wywolywany z CLI)."""
    if not os.path.isdir(root):
        print(f"[!] Nie ma takiego katalogu: {root}")
        sys.exit(1)

    rekordy, global_df = wczytaj_wszystkie(root)
    if not rekordy:
        print("[!] Nie wczytano zadnych danych.")
        sys.exit(1)

    os.makedirs(outdir, exist_ok=True)

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

    out_txt = os.path.join(outdir, "RAPORT_ZBIORCZY_KRZYZOWY.txt")
    out_csv = os.path.join(outdir, "RAPORT_ZBIORCZY_KRZYZOWY.csv")
    generuj_raport_zbiorczy(rekordy, bezposrednia, wspolne, imei_df, out_txt, out_csv)

    print("\n" + "=" * 100)
    print("  PODSUMOWANIE ANALIZY KRZYZOWEJ")
    print("=" * 100)
    print(f"  Abonentow: {len(rekordy)}")
    print(f"  Bezposrednich polaczen miedzy abonentami: {len(bezposrednia)} kierunkow")
    print(f"  Wspolnych kontaktow osob trzecich: {len(wspolne)} numerow")
    print(f"  Wspolnych urzadzen (IMEI): {len(imei_df)}")
    print("=" * 100)
    print(f"\n[+] RAPORT ZBIORCZY TXT: {os.path.abspath(out_txt)}")
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
