"""Livello di ingresso/uscita: lettura dell'elenco delle Sedi tecniche da file
Excel o CSV, elaborazione tramite il nucleo e salvataggio dell'output.

Questo modulo non contiene logica di conversione: tutta la conversione è
delegata a conversione_sedi.nucleo. Può essere importato da altri programmi
(es. interfaccia grafica) oppure usato tramite la riga di comando (cli.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from conversione_sedi.nucleo import (
    Configurazione,
    ErroreConfigurazione,
    carica_configurazione,
    elabora_dataframe,
    leggi_csv,
    riepilogo,
)

# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------
CARTELLA_CONFIG = Path(__file__).resolve().parent.parent / "config"
REGOLE_PREDEFINITE = CARTELLA_CONFIG / "regole.csv"
TRASFORMAZIONI_PREDEFINITE = CARTELLA_CONFIG / "trasformazioni.csv"

# Nomi di colonna riconosciuti automaticamente per la Sede_tecnica
# (confronto senza distinzione tra maiuscole/minuscole, spazi e "_").
COLONNE_SEDE_PREDEFINITE = ("Sede tecnica", "Sede_tecnica")

COLONNE_OUTPUT = ("Codice_Out", "Nuova_Sede_Tecnica", "Esito")

ESTENSIONI_EXCEL = (".xlsx", ".xlsm")
ESTENSIONI_CSV = (".csv",)
SUFFISSO_OUTPUT = "_convertito"


# ---------------------------------------------------------------------------
# Strutture dati
# ---------------------------------------------------------------------------
class ErroreDati(Exception):
    """Errore bloccante nella lettura o scrittura del file delle Sedi tecniche."""

    def __init__(self, errori: list[str]):
        self.errori = list(errori)
        super().__init__("\n".join(self.errori))


@dataclass
class EsitoElaborazione:
    dati: pd.DataFrame                  # DataFrame di output (input + 3 colonne)
    riepilogo: dict[str, int]
    percorso_output: Path | None = None
    avvisi: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Lettura
# ---------------------------------------------------------------------------
def _chiave_colonna(nome: object) -> str:
    return str(nome).strip().casefold().replace("_", " ")


def trova_colonna_sede(df: pd.DataFrame, colonna: str | None = None) -> str:
    """Individuazione della colonna delle Sedi tecniche.
    Se colonna è None si cercano i nomi predefiniti (COLONNE_SEDE_PREDEFINITE).
    Il confronto ignora maiuscole/minuscole, spazi esterni e la differenza
    tra spazio e "_". Restituisce il nome effettivo della colonna."""
    cercate = (colonna,) if colonna else COLONNE_SEDE_PREDEFINITE
    chiavi = {_chiave_colonna(c) for c in cercate}
    trovate = [c for c in df.columns if _chiave_colonna(c) in chiavi]
    if len(trovate) == 1:
        return trovate[0]
    elenco = ", ".join(f"\"{c}\"" for c in df.columns) or "(nessuna)"
    nomi = " o ".join(f"\"{c}\"" for c in cercate)
    if not trovate:
        raise ErroreDati([f"Colonna delle Sedi tecniche {nomi} non trovata. "
                          f"Colonne presenti: {elenco}."])
    raise ErroreDati([f"Colonna delle Sedi tecniche {nomi} presente più volte. "
                      f"Colonne presenti: {elenco}."])


def leggi_sedi(percorso: str | Path, foglio: str | None = None) -> pd.DataFrame:
    """Lettura del file delle Sedi tecniche (Excel o CSV) come testo puro
    (dtype=str, keep_default_na=False). Per i file Excel si legge il foglio
    indicato per nome, altrimenti il primo."""
    percorso = Path(percorso)
    if not percorso.is_file():
        raise ErroreDati([f"File non trovato: {percorso}"])
    estensione = percorso.suffix.lower()

    if estensione in ESTENSIONI_CSV:
        try:
            return leggi_csv(percorso)
        except ErroreConfigurazione as e:
            raise ErroreDati(e.errori) from None

    if estensione in ESTENSIONI_EXCEL:
        try:
            with pd.ExcelFile(percorso, engine="openpyxl") as xl:
                if foglio is not None and foglio not in xl.sheet_names:
                    raise ErroreDati([f"{percorso.name}: foglio \"{foglio}\" non trovato. "
                                      f"Fogli presenti: {', '.join(xl.sheet_names)}."])
                return xl.parse(0 if foglio is None else foglio,
                                dtype=str, keep_default_na=False, na_filter=False)
        except ErroreDati:
            raise
        except PermissionError:
            raise ErroreDati([f"Impossibile leggere {percorso.name}: "
                              "il file è aperto in un altro programma?"]) from None
        except Exception as e:      # file danneggiato o non Excel
            raise ErroreDati([f"Impossibile leggere {percorso.name}: {e}"]) from None

    raise ErroreDati([f"Formato di file non supportato: \"{percorso.suffix}\". "
                      "Usare .xlsx, .xlsm o .csv."])


# ---------------------------------------------------------------------------
# Scrittura
# ---------------------------------------------------------------------------
def percorso_output_predefinito(percorso_input: str | Path) -> Path:
    """<nome>_convertito.<estensione> nella stessa cartella dell'input
    (i file .xlsm vengono salvati come .xlsx, senza macro)."""
    p = Path(percorso_input)
    estensione = ".xlsx" if p.suffix.lower() in ESTENSIONI_EXCEL else p.suffix.lower()
    return p.with_name(p.stem + SUFFISSO_OUTPUT + estensione)


def _scrivi_excel(df: pd.DataFrame, percorso: Path) -> None:
    """Scrittura in Excel con tutte le celle in formato testo, così che valori
    come "++E-..." o "01" non vengano interpretati come formule o numeri."""
    with pd.ExcelWriter(percorso, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sedi tecniche")
        foglio = writer.sheets["Sedi tecniche"]
        for colonna in foglio.iter_cols():
            larghezza = 0
            for cella in colonna:
                if isinstance(cella.value, str):
                    cella.data_type = "s"           # mai formula
                cella.number_format = "@"           # formato Testo
                larghezza = max(larghezza, len(str(cella.value or "")))
            foglio.column_dimensions[colonna[0].column_letter].width = min(larghezza + 2, 60)
        foglio.freeze_panes = "A2"
        foglio.auto_filter.ref = foglio.dimensions


def scrivi_output(df: pd.DataFrame, percorso: str | Path) -> Path:
    """Salvataggio del DataFrame elaborato in Excel (.xlsx) o CSV (";", UTF-8
    con BOM, leggibile direttamente da Excel)."""
    percorso = Path(percorso)
    estensione = percorso.suffix.lower()
    if estensione not in (".xlsx", ".csv"):
        raise ErroreDati([f"Formato di output non supportato: \"{percorso.suffix}\". "
                          "Usare .xlsx o .csv."])
    if not percorso.parent.is_dir():
        raise ErroreDati([f"Cartella di destinazione inesistente: {percorso.parent}"])
    try:
        if estensione == ".xlsx":
            _scrivi_excel(df, percorso)
        else:
            df.to_csv(percorso, sep=";", index=False, encoding="utf-8-sig")
    except PermissionError:
        raise ErroreDati([f"Impossibile scrivere {percorso.name}: "
                          "il file è aperto in un altro programma?"]) from None
    return percorso


# ---------------------------------------------------------------------------
# Elaborazione completa
# ---------------------------------------------------------------------------
def elabora(df: pd.DataFrame, conf: Configurazione,
            colonna: str | None = None) -> EsitoElaborazione:
    """Elaborazione di un DataFrame già disponibile (es. da interfaccia grafica)."""
    nome_colonna = trova_colonna_sede(df, colonna)
    avvisi = list(conf.avvisi)
    sovrascritte = [c for c in COLONNE_OUTPUT if c in df.columns]
    if sovrascritte:
        avvisi.append("Colonne già presenti nell'input, sostituite dall'elaborazione: "
                      + ", ".join(sovrascritte) + ".")
    out = elabora_dataframe(df, conf, nome_colonna)
    return EsitoElaborazione(out, riepilogo(out), None, avvisi)


def converti_file(percorso_input: str | Path,
                  percorso_output: str | Path | None = None,
                  percorso_regole: str | Path = REGOLE_PREDEFINITE,
                  percorso_trasformazioni: str | Path = TRASFORMAZIONI_PREDEFINITE,
                  colonna: str | None = None,
                  foglio: str | None = None) -> EsitoElaborazione:
    """Caricamento della configurazione, lettura delle Sedi tecniche,
    elaborazione e salvataggio. Solleva ErroreConfigurazione o ErroreDati."""
    percorso_input = Path(percorso_input)
    uscita = Path(percorso_output) if percorso_output else percorso_output_predefinito(percorso_input)
    if uscita.resolve() == percorso_input.resolve():
        raise ErroreDati(["Il file di output non può coincidere con il file di input."])

    conf = carica_configurazione(percorso_regole, percorso_trasformazioni)
    df = leggi_sedi(percorso_input, foglio)
    esito = elabora(df, conf, colonna)
    esito.percorso_output = scrivi_output(esito.dati, uscita)
    return esito
