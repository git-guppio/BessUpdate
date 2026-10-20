"""Colori delle tabelle (SPECIFICHE_GUI.md, sezione 3.3), senza dipendenze Qt.

- colore del testo = origine del dato: nero importato, blu manuale/modificato,
  grigio barrato per le righe rimosse;
- colore di sfondo = esito: rosso chiaro errore, giallo da verificare,
  grigio escluso.
"""
from __future__ import annotations

from dataclasses import dataclass

from conversione_sedi.tabella import MetaRiga

ROSSO = "#F8D7DA"
GIALLO = "#FFF3CD"
GRIGIO = "#E9ECEF"
BLU = "#0B5ED7"
GRIGIO_TESTO = "#8A9198"
TESTO = "#212529"                   # testo normale sugli sfondi colorati

_ROSSI = {"Conflitto", "Mancante in SAP", "In eccesso in SAP", "Sede vuota", "Con errori"}
_GIALLI = {"Da verificare", "Da decidere", "DA_VERIFICARE", "In sospeso", "Caricato - da validare"}
_GRIGI = {"NESSUNA_CORRISPONDENZA"}


def sfondo_esito(valore) -> str | None:
    """Colore di sfondo per il valore di una colonna di esito (None = nessuno)."""
    v = "" if valore is None else str(valore)
    if v in _ROSSI or v.startswith("Parent NOK") or "Valore duplicato" in v:
        return ROSSO
    if v in _GIALLI or v.startswith("Descrizione diversa"):
        return GIALLO
    if v in _GRIGI or v.startswith("Esclusa"):
        return GRIGIO
    return None


@dataclass(frozen=True)
class Stile:
    testo: str | None = None
    sfondo: str | None = None
    barrato: bool = False


def stile_cella(meta: MetaRiga | None, colonna: str, esito=None, riga_manuale: bool = False) -> Stile:
    """Stile di una cella: `meta` per le tabelle con modifiche manuali,
    `esito` per lo sfondo, `riga_manuale` per righe derivate da decisioni manuali."""
    sfondo = sfondo_esito(esito)
    if meta is not None and meta.rimossa:
        return Stile(GRIGIO_TESTO, None, True)
    manuale = riga_manuale or (meta is not None and (meta.manuale or colonna in meta.originali))
    return Stile(BLU if manuale else (TESTO if sfondo else None), sfondo, False)
