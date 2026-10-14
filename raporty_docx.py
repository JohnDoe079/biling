#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generatory raportow DOCX (A4) dla toolkitu bilingowego.

Generowane dokumenty:
- raport per numer (analizaBilling.raport_per_numer),
- raport urzadzenia/IMEI (analizaBilling.raport_per_urzadzenie),
- raport zbiorczy krzyzowy (analizaKrzyzowa).

Uklad: orientacja pozioma (landscape) A4 — tabele licznosciowe sa szerokie
i w pionie bylyby nieczytelne. Wymaga: pip install python-docx
(brak biblioteki = komunikat, raporty CSV/TXT generuja sie normalnie).
"""
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from common import format_numer, fmt_czas


# ─────────────────────────────────────────────────────────────────────
# POMOCNICZE
# ─────────────────────────────────────────────────────────────────────

def _dokument(landscape=False):
    """Nowy dokument A4 (portret) z marginesami 1,5 cm."""
    doc = Document()
    sec = doc.sections[0]
    if landscape:
        sec.orientation = WD_ORIENT.LANDSCAPE
        sec.page_width, sec.page_height = Cm(29.7), Cm(21.0)
    else:
        sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    for atrybut in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
        setattr(sec, atrybut, Cm(1.5))
    styl = doc.styles["Normal"]
    styl.font.name = "Calibri"
    styl.font.size = Pt(10)
    return doc


def _tytul(doc, tekst, poziom=1):
    h = doc.add_heading(tekst, level=poziom)
    for run in h.runs:
        run.font.size = Pt(14 if poziom == 1 else 11)
    return h


def _akapit(doc, tekst, bold=False, italic=False, size=10):
    p = doc.add_paragraph()
    run = p.add_run(tekst)
    run.bold = bold
    run.italic = italic
    run.font.size = Pt(size)
    return p


def _cien_naglowka(cell, kolor="D9D9D9"):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), kolor)
    tcPr.append(shd)


def _powtarzaj_naglowek(row):
    """Naglowek tabeli powtarza sie na kazdej kolejnej stronie A4."""
    trPr = row._tr.get_or_add_trPr()
    th = OxmlElement("w:tblHeader")
    th.set(qn("w:val"), "true")
    trPr.append(th)


def _tabela(doc, naglowki, wiersze, font=8, tytul=None):
    """Tabela z formatowaniem; wiersze = lista list (wartosci str/int)."""
    if tytul:
        _tytul(doc, tytul, poziom=2)
    if not wiersze:
        _akapit(doc, "Brak zdarzen w tym okresie.", italic=True)
        return None
    t = doc.add_table(rows=1, cols=len(naglowki))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = True
    # szerokosc tabeli 100% strony (skalowanie na A4 portret)
    tblPr = t._tbl.tblPr
    tblW = tblPr.find(qn("w:tblW"))
    if tblW is None:
        tblW = OxmlElement("w:tblW")
        tblPr.append(tblW)
    tblW.set(qn("w:w"), "5000")   # 5000 = 100% (polfipki procentu)
    tblW.set(qn("w:type"), "pct")
    hdr = t.rows[0]
    for j, h in enumerate(naglowki):
        cell = hdr.cells[j]
        cell.text = str(h)
        for p in cell.paragraphs:
            for r in p.runs:
                r.bold = True
                r.font.size = Pt(font)
        _cien_naglowka(cell)
    _powtarzaj_naglowek(hdr)
    for w in wiersze:
        row = t.add_row()
        for j, v in enumerate(w):
            cell = row.cells[j]
            cell.text = "" if v is None else str(v)
            for p in cell.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(font)
    return t


def _wiersze_df(df, kolumny, fmt=None):
    """DataFrame -> lista wierszy (lista list) wg zadanych kolumn."""
    fmt = fmt or {}
    out = []
    for _, r in df.iterrows():
        out.append([fmt.get(k, lambda x: x)(r[k]) if k in df.columns else ""
                    for k in kolumny])
    return out


def _preambula_doc(doc, pre):
    """Formulka oględzin + listing plikow z SHA-256."""
    _tytul(doc, "OGLĘDZINY DANYCH TELEKOMUNIKACYJNYCH")
    _akapit(doc, "Oględzinom poddano dane telekomunikacyjne dostarczone przez "
                 f"operatora {pre['operator']} dla {pre['cel_txt']} "
                 f"za okres od {pre['od']} do {pre['do']}.")
    _akapit(doc, f"Dane umieszczono w folderze abonenta '{pre['folder']}' ({pre['operator_key']}).")
    if pre.get("pliki"):
        _tabela(doc, ["Lp", "Rola", "Plik", "SHA-256"],
                [[i, pz["rola"], pz["plik"], pz["sha256"]] for i, pz in enumerate(pre["pliki"], 1)],
                font=8, tytul="PLIKI ŹRÓDŁOWE (listing z sumami kontrolnymi SHA-256)")
    else:
        _akapit(doc, "PLIKI ŹRÓDŁOWE: brak rozpoznawalnych plikow w folderze abonenta.",
                italic=True)


def _meta_doc(doc, opisy):
    """Opisy meta: lista (etykieta, wartosc) pomijane gdy puste."""
    for etykieta, wartosc in opisy:
        if wartosc:
            _akapit(doc, f"{etykieta}: {wartosc}", bold=True)


# ─────────────────────────────────────────────────────────────────────
# RAPORT PER NUMER
# ─────────────────────────────────────────────────────────────────────

def raport_numer_docx(outpath, target, kp, ks, bts, imei_df, abonent, inet,
                      okres_od, okres_do, historia_abonentow, historia_kontaktow,
                      bloki, uwagi, pre):
    doc = _dokument(landscape=False)
    _tytul(doc, "RAPORT KONCOWY — ANALIZA BILINGOW")
    _preambula_doc(doc, pre)

    if bloki is None:
        bloki = [{"naglowek": None, "kp": kp, "ks": ks, "bts": bts, "imei": imei_df,
                  "inet": inet, "abonent": abonent, "od": okres_od, "do": okres_do,
                  "historia_kontaktow": historia_kontaktow}]
    main_abonent = abonent if (abonent and abonent.get("nazwa")) else bloki[-1]["abonent"]
    _meta_doc(doc, [
        ("Numer", format_numer(target)),
        ("Abonent", main_abonent.get("nazwa")),
        ("Adres", main_abonent.get("adres")),
        ("PESEL/REGON", main_abonent.get("pesel")),
        ("SIM", main_abonent.get("sim")),
        ("Forma", main_abonent.get("typ_msisdn")),
        ("Status", main_abonent.get("status")),
        ("Okres bilingow", f"{okres_od} - {okres_do}"),
        ("Uwagi", uwagi or ""),
    ])

    if historia_abonentow and target in historia_abonentow and len(historia_abonentow[target]) > 1:
        _tabela(doc, ["Lp", "Data od", "Data do", "Nazwa / Firma", "PESEL/REGON", "Adres"],
                [[i, w.get("data_akt", "-"), w.get("data_dezakt", "-"),
                  w["nazwa"] or "(brak danych)", w["pesel"] or "-", w["adres"] or "(brak danych)"]
                 for i, w in enumerate(historia_abonentow[target], 1)],
                tytul="HISTORIA ZMIAN ABONENTA")

    for bi, blok in enumerate(bloki, 1):
        if blok.get("naglowek"):
            _tytul(doc, blok["naglowek"], poziom=2)
        elif len(bloki) > 1:
            _tytul(doc, f"OKRES {bi}: {blok['od']} – {blok['do']}", poziom=2)

        hk = blok.get("historia_kontaktow")
        if hk:
            wiersze = []
            lp = 1
            for numer, wpisy in sorted(hk.items()):
                for w in wpisy:
                    wiersze.append([lp, format_numer(numer), w.get("data_akt", "-"),
                                    w.get("data_dezakt", "-"), w["nazwa"] or "(brak danych)",
                                    w["pesel"] or "-", w["adres"] or "(brak danych)"])
                    lp += 1
            _tabela(doc, ["Lp", "Numer", "Data od", "Data do", "Nazwa / Firma",
                          "PESEL/REGON", "Adres"], wiersze,
                    tytul="HISTORIA ZMIAN ABONENTOW KONTAKTOW")

        _tabela(doc, ["Lp", "Numer telefonu", "Imie i nazwisko / Firma",
                      "Wych", "Przych", "Proba", "Razem", "Czas wych", "Czas przych", "Zakres czasu"],
                _wiersze_df(blok["kp"],
                            ["numer_kontaktu", "nazwa_kontaktu", "voice_wychodzace",
                             "voice_przychodzace", "proba_razem", "razem",
                             "czas_wychodzacy_s", "czas_przychodzacy_s", "zakres_czasu"],
                            fmt={"numer_kontaktu": format_numer,
                                 "czas_wychodzacy_s": fmt_czas,
                                 "czas_przychodzacy_s": fmt_czas,
                                 "nazwa_kontaktu": lambda x: x or "(brak danych)"}),
                tytul=f"SEKCJA 1: KONTAKTY GŁOSOWE + PRÓBY — okres {bi}")

        _tabela(doc, ["Lp", "Numer telefonu", "Imie i nazwisko / Firma",
                      "Wych", "Przych", "Razem", "Zakres czasu"],
                _wiersze_df(blok["ks"],
                            ["numer_kontaktu", "nazwa_kontaktu", "sms_wychodzace",
                             "sms_przychodzace", "sms_razem", "zakres_czasu"],
                            fmt={"numer_kontaktu": format_numer,
                                 "nazwa_kontaktu": lambda x: x or "(brak danych)"}),
                tytul=f"SEKCJA 2: KONTAKTY SMS/MMS — okres {bi}")

        inet_b = blok["inet"]
        _tabela(doc, ["Opis", "Ilosc sesji", "Suma czasu", "Zakres czasu"],
                [["Internet (DATA)", inet_b["razem"], fmt_czas(inet_b["czas_s"]),
                  inet_b["zakres_czasu"] or "Brak zdarzen"]],
                tytul=f"SEKCJA 3: INTERNET (DATA) — okres {bi}")

        _tabela(doc, ["Lp", "Kod BTS", "Inicjujace", "Odbierajace", "Adres stacji"],
                _wiersze_df(blok["bts"], ["bts", "inicjujace", "odbierajace", "adres_bts"],
                            fmt={"adres_bts": lambda x: x or "(brak danych)"}),
                tytul=f"SEKCJA 4: STACJE BTS — okres {bi}")

        if not blok["imei"].empty:
            _tabela(doc, ["Lp", "IMEI", "Liczba zdarzen", "IMSI", "Uwagi"],
                    _wiersze_df(blok["imei"], ["imei", "liczba_zdarzen", "imsi"],
                                fmt={"imsi": lambda x: x or "-"}),
                    tytul=f"SEKCJA 5: URZĄDZENIA (IMEI) — okres {bi}")

    _akapit(doc, "KONIEC RAPORTU", bold=True)
    doc.save(outpath)
    return outpath


# ─────────────────────────────────────────────────────────────────────
# RAPORT URZADZENIA (IMEI)
# ─────────────────────────────────────────────────────────────────────

def raport_urzadzenie_docx(outpath, imei, numery_df, kontakty_df, imsi_df, bts_df, pre):
    doc = _dokument(landscape=False)
    _tytul(doc, "RAPORT KONCOWY — ANALIZA URZADZENIA (IMEI)")
    _preambula_doc(doc, pre)

    if not numery_df.empty:
        wiersze = []
        for i, (_, r) in enumerate(numery_df.iterrows(), 1):
            razem = int(r["voice"] + r["sms_mms"] + r["proba"] + r["data"])
            wiersze.append([i, format_numer(r["numer"]), r.get("nazwa", "") or "(brak danych)",
                            r["zdarzenia"], r["voice"], r["sms_mms"], r["proba"], r["data"],
                            razem, f'{r["od"]} - {r["do"]}'])
        _tabela(doc, ["Lp", "Numer telefonu", "Imie i nazwisko / Firma", "Zdarzen",
                      "Voice", "SMS/MMS", "Proby", "DATA", "Razem", "Zakres czasu"],
                wiersze, tytul="SEKCJA 1: NUMERY (MSISDN) UZYWANE W URZADZENIU")
        if len(numery_df) > 1:
            _akapit(doc, f"UWAGA: Wykryto {len(numery_df)} roznych numerow uzywanych "
                         f"w urzadzeniu {imei}.", bold=True)
    else:
        _tabela(doc, ["Lp", "Numer telefonu", "Imie i nazwisko / Firma", "Zdarzen",
                      "Voice", "SMS/MMS", "Proby", "DATA", "Razem", "Zakres czasu"],
                [], tytul="SEKCJA 1: NUMERY (MSISDN) UZYWANE W URZADZENIU")

    _tabela(doc, ["Lp", "IMSI", "Liczba zdarzen"],
            _wiersze_df(imsi_df, ["imsi", "zdarzenia"]),
            tytul="SEKCJA 2: KARTY SIM (IMSI) UZYWANE W URZADZENIU")

    if not kontakty_df.empty:
        wiersze = []
        for i, (_, r) in enumerate(kontakty_df.iterrows(), 1):
            wiersze.append([i, format_numer(r["numer"]),
                            r.get("nazwa", "") or "(brak danych)",
                            r["zdarzenia"], f'{r["od"]} - {r["do"]}'])
        _tabela(doc, ["Lp", "Numer telefonu", "Imie i nazwisko / Firma", "Zdarzen", "Zakres czasu"],
                wiersze, tytul="SEKCJA 3: KONTAKTY URZADZENIA")
    else:
        _tabela(doc, ["Lp", "Numer telefonu", "Imie i nazwisko / Firma", "Zdarzen", "Zakres czasu"],
                [], tytul="SEKCJA 3: KONTAKTY URZADZENIA")

    _tabela(doc, ["Lp", "Kod BTS", "Liczba zdarzen"],
            _wiersze_df(bts_df, ["bts", "zdarzenia"]),
            tytul="SEKCJA 4: STACJE BTS")

    _akapit(doc, "KONIEC RAPORTU", bold=True)
    doc.save(outpath)
    return outpath


# ─────────────────────────────────────────────────────────────────────
# RAPORT ZBIORCZY KRZYZOWY
# ─────────────────────────────────────────────────────────────────────

def raport_krzyzowy_docx(outpath, rekordy, osoby, kom_osob, wspolne, imei_df, wygenerowano):
    doc = _dokument(landscape=False)
    _tytul(doc, "RAPORT ZBIORCZY — ANALIZA KRZYZOWA BILINGOW")
    _akapit(doc, f"Wygenerowano: {wygenerowano}")
    _akapit(doc, f"Analizowanych numerow: {len(rekordy)} | Osob/firm: {len(osoby)}")

    _tabela(doc, ["Lp", "Nazwa / Firma", "PESEL/NIP-KRS", "Numery (MSISDN)",
                  "Operatorzy", "Urzadzenia (IMEI)", "Zdarzen"],
            [[i, o["nazwa"] or "(brak danych)",
              klucz if not klucz.startswith("MSISDN:") else "",
              ", ".join(format_numer(n) for n in o["numery"]),
              ", ".join(sorted(o["operatory"])),
              ", ".join(sorted(o["imei"])) if o["imei"] else "-",
              o["zdarzen"]]
             for i, (klucz, o) in enumerate(osoby.items(), 1)],
            tytul="SEKCJA A: ANALIZOWANE OSOBY / FIRMY (grupowanie po PESEL / NIP-KRS)")

    _tabela(doc, ["Lp", "Folder abonenta", "Numer (MSISDN)", "PESEL/NIP-KRS",
                  "Operator", "Okres od", "Okres do", "Zdarzenia"],
            [[i, r["abonent"], format_numer(r["numer"]) if r["numer"] else "-",
              r.get("identyfikator", ""), r["operator"],
              r["okres_od"], r["okres_do"], len(r["df"])]
             for i, r in enumerate(rekordy, 1)],
            tytul="SEKCJA A2: WYKAZ ANALIZOWANYCH NUMEROW (MSISDN)")

    if not kom_osob.empty:
        wiersze = []
        for i, (_, r) in enumerate(kom_osob.iterrows(), 1):
            ko = r["od_klucz"] if not str(r["od_klucz"]).startswith("MSISDN:") else "-"
            kd = r["do_klucz"] if not str(r["do_klucz"]).startswith("MSISDN:") else "-"
            wiersze.append([i, r["od_osoba"], ko, r["do_osoba"], kd,
                            r.get("ta_sama_osoba", ""), r["voice"], r["proby"],
                            r["sms_mms"], r["razem"],
                            f'{r["zakres_od"]} - {r["zakres_do"]}'])
        _tabela(doc, ["Lp", "Osoba/Firma (od)", "PESEL/NIP od", "Osoba/Firma (do)",
                      "PESEL/NIP do", "Oso.", "Voice", "Proby", "SMS/MMS", "Razem", "Zakres czasu"],
                wiersze, tytul="SEKCJA B: KOMUNIKACJA MIEDZY OSOBAMI / FIRMAMI")
    else:
        _tabela(doc, ["Komunikacja"], [], tytul="SEKCJA B: KOMUNIKACJA MIEDZY OSOBAMI / FIRMAMI")

    if not wspolne.empty:
        _tabela(doc, ["Lp", "Numer kontaktu", "Liczba abonentow", "Razem zdarzen",
                      "Abonenci laczeni tym numerem"],
                _wiersze_df(wspolne, ["numer_kontaktu", "liczba_abonentow",
                                      "razem_zdarzen", "abonenci"],
                            fmt={"numer_kontaktu": format_numer}),
                tytul="SEKCJA C: OSOBY TRZECIE LACZACE ABONENTOW (wspolne kontakty)")
    else:
        _tabela(doc, ["Wspolne kontakty"], [],
                tytul="SEKCJA C: OSOBY TRZECIE LACZACE ABONENTOW")

    if not imei_df.empty:
        _tabela(doc, ["Lp", "IMEI", "Liczba abonentow", "Abonenci"],
                _wiersze_df(imei_df, ["imei", "liczba_abonentow", "abonenci"]),
                tytul="SEKCJA D: URZADZENIA (IMEI) WSPOLNE DLA WIECEJ NIZ JEDNEGO ABONENTA")
    else:
        _tabela(doc, ["Wspolne IMEI"], [], tytul="SEKCJA D: WSPOLNE URZADZENIA (IMEI)")

    _akapit(doc, "KONIEC RAPORTU ZBIORCZEGO", bold=True)
    doc.save(outpath)
    return outpath
