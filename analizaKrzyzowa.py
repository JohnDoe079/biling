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
            "parse": plus.parse_plus},
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
            pliki = info["modul"].autodetect(folder)
        except Exception as e:
            print(f"[!] {operator}/{abonent}: blad autodetekcji: {e}")
            continue

        if verbose:
            print(f"\n[+] {operator}/{abonent}")
            for rola, p in pliki.items():
                if p:
                    print(f"    {rola}: {os.path.basename(p)}")

        if not pliki.get("wykaz"):
            print(f"[!] {operator}/{abonent}: nie znaleziono pliku z wykazem polaczen — pominięto.")
            continue

        try:
            df, msisdn = info["parse"](pliki["wykaz"], verbose=verbose)
        except BrakParsaraError as e:
            print(f"[!] {e}")
            continue
        except Exception as e:
            print(f"[!] {operator}/{abonent}: blad parsowania wykazu: {e}")
            continue

        if df is None or df.empty:
            print(f"[!] {operator}/{abonent}: brak sparsowanych rekordow.")
            continue

        numer = wykryj_numer_abonenta(df, msisdn, abonent)
        nazwiska_map, historia = {}, {}
        if pliki.get("nazwiska") and info.get("parse_nazwiska"):
            try:
                nazwiska_map, historia = info["parse_nazwiska"](pliki["nazwiska"], verbose=False)
            except Exception as e:
                print(f"    [!] blad parsowania danych osobowych: {e}")
        bts_map = {}
        if pliki.get("bts") and info.get("parse_bts"):
            try:
                bts_map = info["parse_bts"](pliki["bts"], verbose=False)
            except Exception as e:
                print(f"    [!] blad parsowania BTS: {e}")

        od, do = okres_bilingow(df)
        df = df.copy()
        df["abonent"] = abonent
        df["operator"] = operator
        df["a_key"] = df["strona_a"].map(klucz_numer)
        df["b_key"] = df["strona_b"].map(klucz_numer)
        ramki.append(df)

        rekordy.append({
            "operator": operator, "abonent": abonent, "numer": numer,
            "folder": folder, "df": df, "nazwiska_map": nazwiska_map,
            "historia": historia, "bts_map": bts_map,
            "okres_od": od, "okres_do": do,
        })
        print(f"    -> numer: {numer} | rekordow: {len(df)} | okres: {od} - {do}")

    global_df = pd.concat(ramki, ignore_index=True) if ramki else pd.DataFrame()
    return rekordy, global_df


# ══════════════════════════════════════════════════════════════════════
# ANALIZA KRZYZOWA
# ══════════════════════════════════════════════════════════════════════

def komunikacja_bezposrednia(rekordy):
    """
    Laczy abonentow ze soba: zdarzenie, w ktorym strona A nalezy do abonenta X
    a strona B do abonenta Y (lub odwrotnie). Zwraca DataFrame par.
    """
    numery = {r["numer"]: r for r in rekordy if r["numer"]}
    wiersze = []
    for rx, ry in itertools.permutations(rekordy, 2):
        nx, ny = rx["numer"], ry["numer"]
        if not nx or not ny or nx == ny:
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
        wiersze.append({
            "od": rx["abonent"], "numer_od": nx, "operator_od": rx["operator"],
            "do": ry["abonent"], "numer_do": ny, "operator_do": ry["operator"],
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
    zbior_numerow = {r["numer"] for r in rekordy if r["numer"]}
    kontakty = {}  # klucz_numer -> {abonent_key: liczba}
    dane_osob = {}
    for r in rekordy:
        df = r["df"]
        klucz_ab = f'{r["abonent"]} [{r["numer"]}]'
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

    # SEKCJA A — abonenci
    L.append("-" * 110)
    L.append("  SEKCJA A: ANALIZOWANI ABONENCI")
    L.append("-" * 110)
    L.append("  {:>3} {:<28} {:<14} {:<10} {:<12} {:<12} {:>8}".format(
        "Lp", "Folder abonenta", "Numer", "Operator", "Okres od", "Okres do", "Zdarzenia"))
    L.append("-" * 110)
    for i, r in enumerate(rekordy, 1):
        L.append("  {:>3} {:<28} {:<14} {:<10} {:<12} {:<12} {:>8}".format(
            i, r["abonent"][:28], r["numer"] or "-", r["operator"],
            r["okres_od"], r["okres_do"], len(r["df"])))
    L.append("")

    # SEKCJA B — bezposrednia
    L.append("-" * 110)
    L.append("  SEKCJA B: KOMUNIKACJA BEZPOSREDNIA MIEDZY ANALIZOWANYMI ABONENTAMI")
    L.append("-" * 110)
    if not bezposrednia.empty:
        L.append("  {:>3} {:<28} {:<28} {:>6} {:>6} {:>8} {:>7} {:<23}".format(
            "Lp", "Abonent (od)", "Abonent (do)", "Voice", "Proby", "SMS/MMS", "Razem", "Zakres czasu"))
        L.append("-" * 110)
        for i, (_, r) in enumerate(bezposrednia.iterrows(), 1):
            L.append("  {:>3} {:<28} {:<28} {:>6} {:>6} {:>8} {:>7} {:<23}".format(
                i, r["od"][:28], r["do"][:28], r["voice"], r["proby"], r["sms_mms"], r["razem"],
                f'{r["zakres_od"]} - {r["zakres_do"]}'))
    else:
        L.append("  Brak bezposredniej komunikacji miedzy analizowanymi abonentami.")
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
                i, r["numer_kontaktu"], r["liczba_abonentow"], r["razem_zdarzen"],
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
        w.writerow(["ABONENCI"])
        w.writerow(["Folder", "Numer", "Operator", "Okres od", "Okres do", "Liczba zdarzen"])
        for r in rekordy:
            w.writerow([r["abonent"], r["numer"], r["operator"], r["okres_od"], r["okres_do"], len(r["df"])])
        w.writerow([])
        w.writerow(["KOMUNIKACJA BEZPOSREDNIA"])
        w.writerow(["Abonent (od)", "Numer od", "Operator od", "Abonent (do)", "Numer do", "Operator do",
                    "Voice", "Proby", "SMS/MMS", "Razem", "Zakres od", "Zakres do"])
        if not bezposrednia.empty:
            for _, r in bezposrednia.iterrows():
                w.writerow([r["od"], r["numer_od"], r["operator_od"], r["do"], r["numer_do"], r["operator_do"],
                            r["voice"], r["proby"], r["sms_mms"], r["razem"], r["zakres_od"], r["zakres_do"]])
        w.writerow([])
        w.writerow(["WSPOLNE KONTAKTY OSOB TRZECICH"])
        w.writerow(["Numer kontaktu", "Liczba abonentow", "Razem zdarzen", "Abonenci"])
        if not wspolne.empty:
            for _, r in wspolne.iterrows():
                w.writerow([r["numer_kontaktu"], r["liczba_abonentow"], r["razem_zdarzen"], r["abonenci"]])
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

def main():
    ap = argparse.ArgumentParser(description="Analiza krzyzowa bilingow (multi-operator)")
    ap.add_argument("--dane", help="katalog glowny ze struktura <operator>/<abonent>/")
    ap.add_argument("--outdir", default="./raport_krzyzowy")
    ap.add_argument("--bez-per-numer", action="store_true", help="pomin klasyczne raporty per numer")
    args = ap.parse_args()

    root = args.dane
    if not root:
        root = input_path("Podaj sciezke do katalogu glownego z danymi (<operator>/<abonent>/): ").strip()
    if not os.path.isdir(root):
        print(f"[!] Nie ma takiego katalogu: {root}")
        sys.exit(1)

    rekordy, global_df = wczytaj_wszystkie(root)
    if not rekordy:
        print("[!] Nie wczytano zadnych danych.")
        sys.exit(1)

    os.makedirs(args.outdir, exist_ok=True)

    if not args.bez_per_numer:
        print("\n[+] Raporty per numer:")
        for r in rekordy:
            try:
                raport_per_numer(r, args.outdir)
            except Exception as e:
                print(f"    [!] {r['abonent']}: blad raportu: {e}")

    bezposrednia = komunikacja_bezposrednia(rekordy)
    wspolne = wspolne_kontakty(rekordy)
    imei_df = wspolne_imei(rekordy)

    out_txt = os.path.join(args.outdir, "RAPORT_ZBIORCZY_KRZYZOWY.txt")
    out_csv = os.path.join(args.outdir, "RAPORT_ZBIORCZY_KRZYZOWY.csv")
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


if __name__ == "__main__":
    main()
