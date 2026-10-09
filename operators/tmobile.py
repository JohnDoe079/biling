#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parsery dla operatora T-Mobile Polska — SKELET (czeka na przykladowy biling do dopasowania wzorcow)."""
import glob
import os
import re

import pandas as pd

from common import pdf_to_text, normalizuj_numer, klucz_numer
from operators.base import parser_niedosteppny


# ─────────────────────────────────────────────────────────────────────
# AUTODETEKCJA PLIKOW W FOLDERZE ABONENTA
# ─────────────────────────────────────────────────────────────────────
# TODO: dopasuj wzorce nazw po dostarczeniu przykladowych plikow T-Mobile Polska.

def autodetect(folder: str):
    pdfs = sorted(glob.glob(os.path.join(folder, "*.pdf")))
    csvs = sorted(glob.glob(os.path.join(folder, "*.csv")))
    xls  = sorted(glob.glob(os.path.join(folder, "*.xls*")))
    pliki = pdfs + csvs + xls
    if not pliki:
        return {"wykaz": None, "nazwiska": None, "bts": None}
    # Heurystyka: plik z "bts" w nazwie -> bts, z "dane"/"abonent"/"nazw" -> nazwiska,
    # pozostale -> wykaz (najwiekszy pierwszy).
    wykaz, nazwiska, bts = None, None, None
    pozostale = []
    for p in pliki:
        n = os.path.basename(p).lower()
        if "bts" in n:
            bts = bts or p
        elif any(k in n for k in ("dane", "abonent", "nazw", "subscr", "personal")):
            nazwiska = nazwiska or p
        else:
            pozostale.append(p)
    if pozostale:
        pozostale.sort(key=lambda p: os.path.getsize(p), reverse=True)
        wykaz = pozostale[0]
    return {"wykaz": wykaz, "nazwiska": nazwiska, "bts": bts}


# ─────────────────────────────────────────────────────────────────────
# PARSERY — SKELETY
# ─────────────────────────────────────────────────────────────────────

parse = parser_niedosteppny("T-Mobile Polska")
parse_nazwiska = parser_niedosteppny("T-Mobile Polska")
parse_bts = parser_niedosteppny("T-Mobile Polska")
