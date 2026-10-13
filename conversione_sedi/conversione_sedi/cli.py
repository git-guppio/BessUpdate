"""Interfaccia a riga di comando.

Esempio:
    python -m conversione_sedi sedi.xlsx
    python -m conversione_sedi sedi.csv -o risultato.xlsx --colonna "FL"
"""
from __future__ import annotations

import argparse
import sys

from conversione_sedi.ingresso_uscita import (
    REGOLE_PREDEFINITE,
    TRASFORMAZIONI_PREDEFINITE,
    ErroreDati,
    converti_file,
)
from conversione_sedi.nucleo import ErroreConfigurazione

CODICE_OK = 0
CODICE_ERRORE = 1


def crea_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="conversione-sedi",
        description="Conversione delle Sedi tecniche in Nuove Sedi tecniche.",
    )
    parser.add_argument("input", help="file delle Sedi tecniche (.xlsx, .xlsm o .csv)")
    parser.add_argument("-o", "--output",
                        help="file di output (.xlsx o .csv); "
                             "predefinito: <input>_convertito.<estensione>")
    parser.add_argument("-c", "--colonna",
                        help="nome della colonna delle Sedi tecniche; "
                             "predefinito: \"Sede tecnica\" o \"Sede_tecnica\"")
    parser.add_argument("-f", "--foglio",
                        help="nome del foglio Excel da leggere; predefinito: il primo")
    parser.add_argument("--regole", default=str(REGOLE_PREDEFINITE),
                        help="file CSV delle regole (predefinito: config/regole.csv)")
    parser.add_argument("--trasformazioni", default=str(TRASFORMAZIONI_PREDEFINITE),
                        help="file CSV delle trasformazioni "
                             "(predefinito: config/trasformazioni.csv)")
    return parser


def _stampa_elenco(titolo: str, righe: list[str], flusso) -> None:
    print(titolo, file=flusso)
    for riga in righe:
        print(f"  - {riga}", file=flusso)


def main(argv: list[str] | None = None) -> int:
    args = crea_parser().parse_args(argv)
    try:
        esito = converti_file(args.input, args.output, args.regole, args.trasformazioni,
                              args.colonna, args.foglio)
    except ErroreConfigurazione as e:
        _stampa_elenco("ERRORE nei file delle regole:", e.errori, sys.stderr)
        return CODICE_ERRORE
    except ErroreDati as e:
        _stampa_elenco("ERRORE:", e.errori, sys.stderr)
        return CODICE_ERRORE

    if esito.avvisi:
        _stampa_elenco("Avvisi:", esito.avvisi, sys.stderr)

    totale = sum(esito.riepilogo.values())
    print(f"Elaborate {totale} righe.")
    larghezza = max(len(e) for e in esito.riepilogo)
    for nome, numero in esito.riepilogo.items():
        print(f"  {nome:<{larghezza}}  {numero}")
    print(f"Output salvato in: {esito.percorso_output}")
    return CODICE_OK


if __name__ == "__main__":
    sys.exit(main())
