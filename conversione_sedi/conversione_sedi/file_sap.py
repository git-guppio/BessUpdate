"""Scrittura dei file di caricamento in SAP dal piano (SPECIFICHE_SAP_SCRIPT.md, 5.4).

- Modifica e Rimozione: transazione ZPM4R_FL_DES_MA_LOAD (tracciato CC04),
  file Excel 97-2003 (.xls), foglio "Foglio1";
- Modifica descrizione: ZPM4R_CREA_FL, testo separato da tabulazioni,
  Windows-1252 senza BOM, righe CRLF;
- Creazione: file Excel (.xlsx) con le colonne "FL" e "Descriptions", per il
  programma esterno di creazione delle sedi tecniche.

Le intestazioni CC04 e ZPM4R sono quelle dei template SAP, copiate in config/.
"""
from __future__ import annotations

from pathlib import Path

from conversione_sedi.ingresso_uscita import CARTELLA_CONFIG, ErroreDati
from conversione_sedi.piano_sap import Piano, Step, TipoStep

CODIFICA_TXT = "cp1252"
FINE_RIGA = "\r\n"

NOMI_BASE = {
    TipoStep.CREAZIONE: "FL_da_creare",
    TipoStep.MODIFICA: "ZPM4R_FL_DES_MA_LOAD_mod",
    TipoStep.RIMOZIONE: "ZPM4R_FL_DES_MA_LOAD_rim",
    TipoStep.DESCRIZIONE: "ZPM4R_CREA_FL_mod",
}
ESTENSIONI = {
    TipoStep.CREAZIONE: ".xlsx",
    TipoStep.MODIFICA: ".xls",
    TipoStep.RIMOZIONE: ".xls",
    TipoStep.DESCRIZIONE: ".txt",
}
FILE_DISPONIBILE = {tipo: True for tipo in TipoStep}
# nomi usati da versioni precedenti, eliminati a ogni generazione
# (nomi brevi perché il campo file delle transazioni accetta al massimo 126 caratteri)
NOMI_PRECEDENTI = ("CC04_modificare_upload", "CC04_rimuovere_upload", "ZPM4R_CREA_FL_crea_upload",
                   "ZPM4R_FL_DES_MA_LOAD_modificare_upload", "ZPM4R_FL_DES_MA_LOAD_rimuovere_upload",
                   "ZPM4R_CREA_FL_modifica_upload")
COLONNE_CREAZIONE = ("FL", "Descriptions")


def _intestazioni(nome: str) -> list[str]:
    testo = (CARTELLA_CONFIG / nome).read_text(encoding=CODIFICA_TXT)
    return testo.rstrip("\r\n").split("\t")


def intestazioni_zpm4r() -> list[str]:
    return _intestazioni("ZPM4R_CREA_FL_intestazioni.txt")


def intestazioni_cc04() -> list[str]:
    return _intestazioni("CC04_intestazioni.txt")


def nome_file(step: Step) -> str:
    return f"{NOMI_BASE[step.tipo]}_Step_{step.numero}{ESTENSIONI[step.tipo]}"


def country(codice: str) -> str:
    """Primi due caratteri del primo livello (USE-US64-1A -> US)."""
    return codice.split("-")[0][:2]


# ---------------------------------------------------------------------------
# Scrittura
# ---------------------------------------------------------------------------
def _scrivi_xls(percorso: Path, step: Step) -> None:
    import xlwt
    wb = xlwt.Workbook(encoding="utf-8")
    foglio = wb.add_sheet("Foglio1")
    testo = xlwt.easyxf(num_format_str="@")
    for c, nome in enumerate(intestazioni_cc04()):
        foglio.write(0, c, nome, testo)
    for r, riga in enumerate(step.righe, start=1):
        for c, valore in enumerate((riga.sede, riga.nuovo_codice, riga.descrizione, riga.superiore)):
            foglio.write(r, c, valore, testo)
    wb.save(str(percorso))


def _scrivi_creazioni(percorso: Path, step: Step) -> None:
    """File per il programma esterno di creazione: colonne FL e Descriptions,
    celle in formato testo."""
    from openpyxl import Workbook
    wb = Workbook()
    foglio = wb.active
    foglio.title = "Foglio1"
    foglio.append(list(COLONNE_CREAZIONE))
    for riga in step.righe:
        foglio.append([riga.sede, riga.descrizione])
    for colonna in foglio.iter_cols():
        for cella in colonna:
            cella.data_type, cella.number_format = "s", "@"
    foglio.column_dimensions["A"].width = 32
    foglio.column_dimensions["B"].width = 44
    wb.save(percorso)


def _scrivi_descrizioni(percorso: Path, step: Step) -> None:
    colonne = intestazioni_zpm4r()
    i_tplnr, i_pltxt, i_country = (colonne.index(c) for c in ("TPLNR", "PLTXT", "COUNTRY"))
    righe = ["\t".join(colonne)]
    for riga in step.righe:
        valori = [""] * len(colonne)
        valori[i_tplnr], valori[i_pltxt], valori[i_country] = riga.sede, riga.descrizione, country(riga.sede)
        righe.append("\t".join(v.replace("\t", " ") for v in valori))
    testo = FINE_RIGA.join(righe) + FINE_RIGA
    try:
        dati = testo.encode(CODIFICA_TXT)
    except UnicodeEncodeError:
        non_validi = [r.sede for r in step.righe if not _codificabile(r.descrizione)]
        raise ErroreDati(["Descrizioni con caratteri non ammessi nella codifica Windows-1252: "
                          + ", ".join(non_validi[:20]) + "."]) from None
    percorso.write_bytes(dati)


def _codificabile(testo: str) -> bool:
    try:
        testo.encode(CODIFICA_TXT)
        return True
    except UnicodeEncodeError:
        return False


def file_precedenti(cartella: Path) -> list[Path]:
    """File di caricamento generati in precedenza nella cartella."""
    nomi = (*NOMI_BASE.values(), *NOMI_PRECEDENTI)
    return sorted({p for nome in nomi for p in cartella.glob(f"{nome}_Step_*")})


def scrivi_piano(piano: Piano, cartella: str | Path) -> dict[int, Path]:
    """Scrive i file del piano nella cartella (creata se manca), eliminando i
    file di una generazione precedente. Restituisce {numero step: file}."""
    if not piano.valido:
        raise ErroreDati(["Il piano contiene errori: file non generati."] + piano.errori)
    cartella = Path(cartella)
    try:
        cartella.mkdir(parents=True, exist_ok=True)
        for vecchio in file_precedenti(cartella):
            vecchio.unlink()
    except PermissionError as e:
        raise ErroreDati([f"Impossibile preparare la cartella {cartella}: "
                          f"un file è aperto in un altro programma? ({e.filename})"]) from None

    scritti: dict[int, Path] = {}
    for step in piano.step:
        if not FILE_DISPONIBILE[step.tipo]:
            continue
        percorso = cartella / nome_file(step)
        try:
            if step.tipo == TipoStep.DESCRIZIONE:
                _scrivi_descrizioni(percorso, step)
            elif step.tipo == TipoStep.CREAZIONE:
                _scrivi_creazioni(percorso, step)
            else:
                _scrivi_xls(percorso, step)
        except PermissionError:
            raise ErroreDati([f"Impossibile scrivere {percorso.name}: il file è aperto in un altro programma?"]) from None
        scritti[step.numero] = percorso
    return scritti
