"""Configurazione comune dei test.

I test usano una copia fissa delle regole di conversione (tests/dati/), così
da non dipendere dalle regole in config/, che l'utente modifica nel tempo.
"""
from pathlib import Path

DATI = Path(__file__).parent / "dati"
REGOLE_TEST = DATI / "regole_test.csv"
TRASFORMAZIONI_TEST = DATI / "trasformazioni_test.csv"
