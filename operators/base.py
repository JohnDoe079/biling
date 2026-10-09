#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interfejs operatora.

Kazdy modul w tym pakiecie MUSI udostepniac:

    autodetect(folder: str) -> dict
        {"wykaz": path|None, "nazwiska": path|None, "bts": path|None}

    parse(path: str, verbose: bool = False) -> (pd.DataFrame, str|None)
        Kolumny kanoniczne:
            data (YYYY-MM-DD), czas (HH:MM:SS), czas_trwania (int|None),
            typ (VOICE|PRÓBA|SMS|MMS|DATA|FWD|...),
            strona_a, bts_a, imei_a, imsi_a,
            strona_b, bts_b, imei_b, imsi_b
        Zwraca tez MSISDN z naglowka (lub None).

    parse_nazwiska(path, verbose=False) -> (mapping, historia)   [opcjonalnie]
        mapping:  {klucz_numer: {"nazwa","adres","pesel"}}
        historia: {klucz_numer: [{data_akt, data_dezakt, nazwa, pesel, adres}, ...]}

    parse_bts(path, verbose=False) -> {kod_bts: adres}           [opcjonalnie]
"""

class BrakParsaraError(NotImplementedError):
    pass

def parser_niedosteppny(operator_nazwa):
    def _raiser(*a, **kw):
        raise BrakParsaraError(
            f"Parser dla operatora '{operator_nazwa}' nie jest jeszcze zaimplementowany.\n"
            f"  Dostarcz przykladowy plik bilingu tego operatora, aby dopasowac wzorce."
        )
    return _raiser
