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
    klucz_imei,
    dane_abonenta, okres_bilingow, BLANK, NIE_IMEI, _clean_counts,
    pelny_numer)
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
                if len(zestawy) > 1 and numer:
                    etykieta = f"{abonent} ({numer})"
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
    # diagnostyka: folder vs rekordy (nie kazdy folder musi dac rekord — log ponizej)
    _foldery_z_rek = {r["folder"] for r in rekordy}
    for poz in skan:
        if poz["folder"] not in _foldery_z_rek:
            print(f"    [!!] Folder bez rekordu: {poz['operator']}/{poz['abonent']} — sprawdz pliki w folderze")
        elif not any(r["folder"] == poz["folder"] and r["numer"] for r in rekordy):
            print(f"    [!!] Folder z rekordami bez numeru: {poz['operator']}/{poz['abonent']}")
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
            fwd = sub[sub["typ"] == "FWD"]
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
                "fwd_przych": int((fwd["b_key"] == nx).sum()),
                "fwd_wych": int((fwd["a_key"] == nx).sum()),
                "dane": int(len(dane)),
                "okres_od": sub["data"].min(),
                "okres_do": sub["data"].max(),
                "ta_sama_osoba": "TAK" if (ix and iy and ix == iy) else "",
            })
    if not wiersze:
        return pd.DataFrame()
    kol = ["numer_kontaktu", "nazwa_kontaktu", "abonent", "razem",
           "voice_przych", "voice_wych", "proby_przych", "proby_wych",
           "sms_przych", "sms_wych", "fwd_przych", "fwd_wych", "dane",
           "okres_od", "okres_do", "ta_sama_osoba"]
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
        fwd = sub[sub["typ"] == "FWD"]
        return {
            "razem": len(sub),
            "voice_wych": int((voice["a_key"] == numer).sum()),
            "voice_przych": int((voice["b_key"] == numer).sum()),
            "proby_wych": int((proba["a_key"] == numer).sum()),
            "proby_przych": int((proba["b_key"] == numer).sum()),
            "sms_wych": int((sms["a_key"] == numer).sum()),
            "sms_przych": int((sms["b_key"] == numer).sum()),
            "fwd_przych": int((fwd["b_key"] == numer).sum()),
            "fwd_wych": int((fwd["a_key"] == numer).sum()),
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
           "sms_przych", "sms_wych", "fwd_przych", "fwd_wych", "dane", "okres_od", "okres_do"]
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
        imeis = imeis[~imeis.isin(NIE_IMEI) & imeis.notna()].map(klucz_imei).unique()
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

def generuj_raport_zbiorczy_docx(rekordy, bezposrednia, wspolne, imei_df, outpath, ogl=None):
    """Raport zbiorczy krzyzowy w DOCX — sekcje A-D jako tabele, Calibri 10."""
    try:
        from docx import Document
        from docx.shared import Pt
    except ImportError:
        print("[!] Brak 'python-docx' — zbiorczy DOCX pominiety.")
        return False
    from common import pelny_numer, fmt_czas
    doc = Document()
    st = doc.styles['Normal']
    st.font.name = 'Calibri'
    st.font.size = Pt(10)
    for hs in ('Heading 1', 'Heading 2', 'Title'):
        try:
            h = doc.styles[hs]
            h.font.name = 'Calibri'
            h.font.bold = True
        except KeyError:
            pass
    doc.add_heading("ANALIZA KRZYZOWA BILINGOW", 0)
    if ogl:
        doc.add_heading("OGLĘDZINY DANYCH TELEKOMUNIKACYJNYCH", 1)
        t = doc.add_table(rows=0, cols=4)
        t.style = "Table Grid"
        for w in ogl:
            if w and w[0] and str(w[0]).startswith("="):
                continue
            if w and len(w) >= 3 and w[0] == "Lp":
                c = t.add_row().cells
                c[0].text, c[1].text, c[2].text, c[3].text = "Lp", "Plik", "SHA-256", "Rozmiar"
                for cc in c:
                    for r_ in cc.paragraphs[0].runs:
                        r_.bold = True
                continue
            if w and str(w[0]).startswith("FOLDER:"):
                doc.add_paragraph(w[0])
                continue
            if w and len(w) >= 2 and w[0] and str(w[0]).isdigit():
                c = t.add_row().cells
                c[0].text, c[1].text = str(w[0]), str(w[1])
                c[2].text = str(w[2]) if len(w) > 2 else ""
                c[3].text = str(w[3]) if len(w) > 3 else ""
                continue
            if w and str(w[0]).strip():
                doc.add_paragraph(str(w[0]))
    # SEKCJA A
    dir_cnt, sha_cnt = {}, {}
    if bezposrednia is not None and not bezposrednia.empty:
        for _, rr in bezposrednia.iterrows():
            dir_cnt[rr["abonent"]] = dir_cnt.get(rr["abonent"], 0) + int(rr["razem"])
    if wspolne is not None and not wspolne.empty:
        for _, rr in wspolne.iterrows():
            sha_cnt[rr["abonent"]] = sha_cnt.get(rr["abonent"], 0) + int(rr["razem"])
    doc.add_heading("SEKCJA A: ANALIZOWANI ABONENCI — liczniki zdarzen KRZYZOWYCH", 1)
    ta = doc.add_table(rows=1, cols=8)
    ta.style = "Light Grid Accent 1"
    for i2, h in enumerate(["Lp", "Folder abonenta", "Numer (MSISDN)", "PESEL/NIP-KRS", "Operator",
                            "Okres od", "Okres do", "Z innymi / Z kontakt."]):
        ta.rows[0].cells[i2].text = h
    for lp, r in enumerate(rekordy, 1):
        c = ta.add_row().cells
        c[0].text = str(lp)
        c[1].text = r["abonent"]
        c[2].text = pelny_numer(r["numer"]) if r["numer"] else "-"
        c[3].text = r.get("identyfikator", "") or "-"
        c[4].text = r["operator"]
        c[5].text = r["okres_od"] or "-"
        c[6].text = r["okres_do"] or "-"
        c[7].text = f"{dir_cnt.get(r['numer'], 0)} / {sha_cnt.get(r['numer'], 0)}"
    # SEKCJA B
    doc.add_heading("SEKCJA B: KOMUNIKACJA BEZPOSREDNIA MIEDZY ANALIZOWANYMI ABONENTAMI", 1)
    if bezposrednia is not None and not bezposrednia.empty:
        tb = doc.add_table(rows=1, cols=6)
        tb.style = "Light Grid Accent 1"
        for i2, h in enumerate(["Numer abonenta", "Numer drugiego", "Razem", "Voice P/W",
                                "Proby P/W", "SMS P/W + FWD P/W"]):
            tb.rows[0].cells[i2].text = h
        for _, rr in bezposrednia.iterrows():
            c = tb.add_row().cells
            c[0].text = pelny_numer(rr["abonent"])
            c[1].text = pelny_numer(rr["numer_kontaktu"])
            c[2].text = str(rr["razem"])
            c[3].text = f'{rr["voice_przych"]}/{rr["voice_wych"]}'
            c[4].text = f'{rr["proby_przych"]}/{rr["proby_wych"]}'
            c[5].text = (f'SMS {rr["sms_przych"]}/{rr["sms_wych"]}; '
                         f'FWD {rr.get("fwd_przych", 0)}/{rr.get("fwd_wych", 0)}')
    else:
        doc.add_paragraph("Brak bezposredniej komunikacji miedzy analizowanymi abonentami.")
    # SEKCJA C
    doc.add_heading("SEKCJA C: OSOBY TRZECIE LACZACE ABONENTOW (wspolne kontakty)", 1)
    if wspolne is not None and not wspolne.empty:
        tc = doc.add_table(rows=1, cols=4)
        tc.style = "Light Grid Accent 1"
        for i2, h in enumerate(["Numer kontaktu", "Nazwa", "Numer abonenta", "Zdarzen / typy"]):
            tc.rows[0].cells[i2].text = h
        for _, rr in wspolne.iterrows():
            c = tc.add_row().cells
            c[0].text = pelny_numer(rr["numer_kontaktu"])
            c[1].text = str(rr.get("nazwa_kontaktu", ""))
            c[2].text = pelny_numer(rr["abonent"])
            c[3].text = (f'{rr["razem"]} (V {rr["voice_przych"]}/{rr["voice_wych"]}, '
                         f'P {rr["proby_przych"]}/{rr["proby_wych"]}, '
                         f'SMS {rr["sms_przych"]}/{rr["sms_wych"]})')
    else:
        doc.add_paragraph("Brak wspolnych kontaktow osob trzecich.")
    # SEKCJA D
    doc.add_heading("SEKCJA D: URZADZENIA (IMEI) WSPOLNE DLA WIECEJ NIZ JEDNEGO ABONENTA", 1)
    if imei_df is not None and not imei_df.empty:
        td = doc.add_table(rows=1, cols=3)
        td.style = "Light Grid Accent 1"
        for i2, h in enumerate(["IMEI (baza 14 cyfr)", "Liczba abonentow", "Abonenci"]):
            td.rows[0].cells[i2].text = h
        for _, rr in imei_df.iterrows():
            c = td.add_row().cells
            c[0].text = str(rr["imei"])
            c[1].text = str(rr["liczba_abonentow"])
            c[2].text = str(rr["abonenci"])
    else:
        doc.add_paragraph("Brak wspolnych urzadzen (IMEI).")
    for _t in doc.tables:
        ab._styl_tabeli(_t, n_naglowkow=1)
    doc.save(outpath)
    return True


def generuj_raport_zbiorczy(rekordy, bezposrednia, wspolne, imei_df, out_txt, out_csv, ogl=None):
    """Raport zbiorczy krzyzowy — XLSX (TXT wycofany). Sekcje A-D + oględziny."""
    from openpyxl import Workbook as _WB
    from openpyxl.styles import Font as _Font, PatternFill as _Fill
    _wb = _WB()
    _ws = _wb.active
    _ws.title = "Krzyzowy"
    f = None
    w = None

    def _wr(row):
        _ws.append(list(row))

    _wr(["ANALIZA KRZYZOWA BILINGOW"])
    # OGLĘDZINY — jednokrotnie, listing folderow z SHA-256 i rozmiarem
    if ogl:
        for w in ogl:
            _wr(w)
        _wr([""])

    # liczniki zdarzen KRZYZOWYCH per abonent
    dir_cnt, sha_cnt = {}, {}
    if not bezposrednia.empty:
        for _, rr in bezposrednia.iterrows():
            dir_cnt[rr["abonent"]] = dir_cnt.get(rr["abonent"], 0) + int(rr["razem"])
    if not wspolne.empty:
        for _, rr in wspolne.iterrows():
            sha_cnt[rr["abonent"]] = sha_cnt.get(rr["abonent"], 0) + int(rr["razem"])

    # SEKCJA A
    _wr(["SEKCJA A: ANALIZOWANI ABONENCI — liczniki zdarzen KRZYZOWYCH"])
    _wr(["Lp", "Folder abonenta", "Numer (MSISDN)", "PESEL/NIP-KRS", "Operator",
         "Okres od", "Okres do", "Z innymi", "Z kontakt."])
    for lp, r in enumerate(rekordy, 1):
        _wr([lp, r["abonent"], r["numer"] or "-", r.get("identyfikator", "") or "-",
             r["operator"], r["okres_od"], r["okres_do"],
             dir_cnt.get(r["numer"], 0), sha_cnt.get(r["numer"], 0)])
    _wr([""])

    # SEKCJA B
    _wr(["SEKCJA B: KOMUNIKACJA BEZPOSREDNIA MIEDZY ANALIZOWANYMI ABONENTAMI"])
    if not bezposrednia.empty:
        _wr(["Numer abonenta", "Numer drugiego abonenta", "Razem zdarzen", "Voice przych",
             "Voice wych", "Proby przych", "Proby wych", "SMS przych", "SMS wych",
             "FWD przych", "FWD wych", "DATA", "Okres od", "Okres do"])
        for _, r in bezposrednia.iterrows():
            _wr([r["abonent"], r["numer_kontaktu"], r["razem"], r["voice_przych"], r["voice_wych"],
                 r["proby_przych"], r["proby_wych"], r["sms_przych"], r["sms_wych"],
                 r.get("fwd_przych", 0), r.get("fwd_wych", 0), r["dane"],
                 r["okres_od"], r["okres_do"]])
    else:
        _wr(["Brak bezposredniej komunikacji miedzy analizowanymi abonentami."])
    _wr([""])

    # SEKCJA C
    _wr(["SEKCJA C: OSOBY TRZECIE LACZACE ABONENTOW (wspolne kontakty)"])
    if not wspolne.empty:
        _wr(["Numer kontaktu", "Nazwa kontaktu", "Numer abonenta", "Zdarzen z kontaktem",
             "Voice przych", "Voice wych", "Proby przych", "Proby wych", "SMS przych", "SMS wych",
             "FWD przych", "FWD wych", "DATA", "Okres od", "Okres do"])
        for _, r in wspolne.iterrows():
            _wr([r["numer_kontaktu"], r["nazwa_kontaktu"], r["abonent"], r["razem"],
                 r["voice_przych"], r["voice_wych"], r["proby_przych"], r["proby_wych"],
                 r["sms_przych"], r["sms_wych"], r.get("fwd_przych", 0), r.get("fwd_wych", 0),
                 r["dane"], r["okres_od"], r["okres_do"]])
    else:
        _wr(["Brak wspolnych kontaktow osob trzecich."])
    _wr([""])

    # SEKCJA D
    _wr(["SEKCJA D: URZADZENIA (IMEI) WSPOLNE DLA WIECEJ NIZ JEDNEGO ABONENTA"])
    if not imei_df.empty:
        _wr(["IMEI", "Liczba abonentow", "Abonenci"])
        for _, r in imei_df.iterrows():
            _wr([r["imei"], r["liczba_abonentow"], r["abonenci"]])
    else:
        _wr(["Brak wspolnych urzadzen."])
    _wr([""])

    from openpyxl.styles import Font as _CalF
    for _row in _ws.iter_rows():
        for _c in _row:
            _c.font = _CalF(name='Calibri', size=10, bold=_c.font.bold)
    _bold = _Font(name='Calibri', size=10, bold=True)
    _fill = _Fill("solid", fgColor="DDDDDD")
    _sekcja = ("SEKCJA", "RAPORT", "ABONENCI", "KOMUNIKACJA", "WSPOLNE", "WSPOLNY",
               "ANALIZA", "#", "IMEI", "OGLĘDZINY", "FOLDER:")
    for _row in _ws.iter_rows():
        _v = _row[0].value
        if isinstance(_v, str) and _v.startswith(_sekcja):
            for _c in _row:
                _c.font = _bold
                _c.fill = _fill
    from common import cap_kolumny as _ck
    _hdr = {}
    for _col in _ws.columns:
        _lit = _col[0].column_letter
        _h = next((str(c.value) for c in _col[:8]
                   if c.value is not None and str(c.value).strip() and
                   not str(c.value).startswith(("SEKCJA", "=", "ANALIZA", "OGL"))), "")
        _hdr[_lit] = _ck(_h)
    for _col in _ws.columns:
        _lit = _col[0].column_letter
        _szer = max((len(str(_c.value)) for _c in _col if _c.value is not None), default=8)
        _ws.column_dimensions[_lit].width = min(max(_szer + 2, 6), _hdr.get(_lit, 30))
    _wb.save(out_csv)



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
    _op = OPERATORZY.get(r.get("operator", ""), {})
    info_nazwa = _op.get("nazwa", r.get("operator", ""))
    od, do = r["okres_od"], r["okres_do"]

    kp = ab.kontakty_zdarzenia(df, target, nazwiska_map)
    ks = ab.kontakty_sms(df, target, nazwiska_map)
    bts = ab.bts_polaczone(df, target, bts_map)
    imei_df = ab.imei_dla_numeru(df, target, nazwiska_map)
    imsi_df = ab.imsi_dla_numeru(df, target)
    ip_df = ab.ip_dla_numeru(df, target)
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
    p_docx = os.path.join(target_dir, f"{target}_RAPORT_KONCOWY.docx")
    ab.generuj_raport_docx(target, kp, ks, bts, imei_df, abonent_info, inet, od, do, p_docx,
                           historia_ab, hk, bloki=None, imsi_df=imsi_df, ip_df=ip_df,
                           operator_nazwa=info_nazwa)
    p_xlsx = os.path.join(target_dir, f"{target}_RAPORT_KONCOWY.xlsx")
    ab.generuj_raport_csv(target, kp, ks, bts, imei_df, abonent_info, inet, od, do, p_xlsx,
                          historia_ab, hk, bloki=None, imsi_df=imsi_df, ip_df=ip_df,
                          )
    print(f"    raport: {p_docx}")


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

    pominięte = []
    if not bez_per_numer:
        print("\n[+] Raporty per numer:")
        for r in rekordy:
            try:
                raport_per_numer(r, outdir)
            except Exception as e:
                import traceback
                traceback.print_exc()
                pominięte.append((r['abonent'], str(e)))
                print(f"    [!] {r['abonent']}: blad raportu: {e}")
    if pominięte:
        print(f"[!] Pominięto {len(pominięte)} raportow per numer:")
        for ab_n, err in pominięte:
            print(f"    - {ab_n}: {err}")

    bezposrednia = komunikacja_bezposrednia(rekordy)
    wspolne = wspolne_kontakty(rekordy)
    imei_df = wspolne_imei(rekordy)

    from common import preambula_zbiorcza
    ogl_zb = preambula_zbiorcza(rekordy)
    out_docx = os.path.join(krzyz_dir, "RAPORT_ZBIORCZY_KRZYZOWY.docx")
    generuj_raport_zbiorczy_docx(rekordy, bezposrednia, wspolne, imei_df, out_docx, ogl=ogl_zb)
    out_csv = os.path.join(krzyz_dir, "RAPORT_ZBIORCZY_KRZYZOWY.xlsx")
    generuj_raport_zbiorczy(rekordy, bezposrednia, wspolne, imei_df, None, out_csv,
                            ogl=ogl_zb)

    print("\n" + "=" * 100)
    print("  PODSUMOWANIE ANALIZY KRZYZOWEJ")
    print("=" * 100)
    print(f"  Abonentow: {len(rekordy)}")
    print(f"  Bezposrednich polaczen miedzy abonentami: {len(bezposrednia)} kierunkow")
    n_wspolnych = wspolne["numer_kontaktu"].nunique() if not wspolne.empty else 0
    print(f"  Wspolnych kontaktow osob trzecich: {n_wspolnych} numerow ({len(wspolne)} powiazan)")
    print(f"  Wspolnych urzadzen (IMEI): {len(imei_df)}")
    print("=" * 100)
    print(f"\n[+] RAPORTY PER NUMER:    {os.path.abspath(outdir)}")
    print(f"[+] RAPORT ZBIORCZY DOCX: {os.path.abspath(out_docx)}")
    print(f"[+] RAPORT ZBIORCZY XLSX: {os.path.abspath(out_csv)}")


def main():
    ap = argparse.ArgumentParser(description="Analiza krzyzowa bilingow (multi-operator)")
    ap.add_argument("--dane", default="./input", help="katalog glowny ze struktura <operator>/<abonent>/ (domyslnie: ./input)")
    ap.add_argument("--outdir", default="./raport_krzyzowy")
    ap.add_argument("--bez-per-numer", action="store_true", help="pomin klasyczne raporty per numer")
    args = ap.parse_args()
    przebieg(args.dane, args.outdir, args.bez_per_numer)


if __name__ == "__main__":
    main()
