"""Check: verifica, dopo il caricamento in SAP, che la codifica presente in
SAP corrisponda esattamente a quella di New (SPECIFICHE_GUI.md, sezione 4.8).

Il confronto è diretto, codice per codice, senza conversione. I dati SAP
provengono dalla stessa estrazione di Actual (sap.estrai_sedi_ih06).

Tabella risultante (tre colonne):
    Sede tecnica | Descrizione | Esito check
con prima le righe estratte da SAP e in fondo le Sedi di New mancanti in SAP
(codice e descrizione presi da New).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from conversione_sedi.riconciliazione import LIVELLO_MINIMO, livello, normalizza_descrizione, normalizza_sede

COL_SEDE = "Sede tecnica"
COL_DESCRIZIONE = "Descrizione"
COL_ESITO = "Esito check"

ESITO_ALLINEATA = "Allineata"
ESITO_MANCANTE = "Mancante in SAP"
ESITO_ECCESSO = "In eccesso in SAP"
ESITO_DESCRIZIONE = "Descrizione diversa"
ESITO_ESCLUSA = "Esclusa (livello 1-2)"
ESITI = (ESITO_ALLINEATA, ESITO_MANCANTE, ESITO_ECCESSO, ESITO_DESCRIZIONE, ESITO_ESCLUSA)


def esito_descrizione_diversa(descrizione_new: str) -> str:
    return f'{ESITO_DESCRIZIONE} (New: "{descrizione_new}")'


def categoria(esito: str) -> str:
    """Categoria di un esito (per statistiche e filtri)."""
    return ESITO_DESCRIZIONE if esito.startswith(ESITO_DESCRIZIONE) else esito


@dataclass
class Verifica:
    dati: pd.DataFrame
    avvisi: list[str] = field(default_factory=list)

    def conteggi(self) -> dict[str, int]:
        c = self.dati[COL_ESITO].map(categoria).value_counts()
        return {e: int(c.get(e, 0)) for e in ESITI}

    @property
    def totale(self) -> int:
        """Righe confrontate (escluse quelle di livello 1-2)."""
        return sum(n for e, n in self.conteggi().items() if e != ESITO_ESCLUSA)

    def percentuali(self) -> dict[str, float]:
        """Percentuale di ogni esito sul totale confrontato."""
        totale = self.totale
        return {e: (round(100 * n / totale, 1) if totale and e != ESITO_ESCLUSA else 0.0)
                for e, n in self.conteggi().items()}

    @property
    def allineamento(self) -> float:
        """Percentuale di Sedi allineate (100 se non c'è nulla da confrontare)."""
        return self.percentuali()[ESITO_ALLINEATA] if self.totale else 100.0

    @property
    def allineato(self) -> bool:
        return self.conteggi()[ESITO_ALLINEATA] == self.totale

    def filtra(self, categoria_esito: str) -> pd.DataFrame:
        return self.dati[self.dati[COL_ESITO].map(categoria) == categoria_esito]


def _sedi(df: pd.DataFrame, nome: str, avvisi: list[str]) -> dict[str, str]:
    for col in (COL_SEDE, COL_DESCRIZIONE):
        if col not in df.columns:
            raise KeyError(f"{nome}: colonna \"{col}\" non presente.")
    sedi: dict[str, str] = {}
    duplicate = set()
    for s, d in zip(df[COL_SEDE], df[COL_DESCRIZIONE]):
        s = normalizza_sede(s)
        if not s:
            continue
        if s in sedi:
            duplicate.add(s)
            continue
        sedi[s] = "" if d is None or (isinstance(d, float) and pd.isna(d)) else str(d)
    if duplicate:
        avvisi.append(f"{nome}: Sedi tecniche duplicate ignorate (vale la prima): "
                      + ", ".join(sorted(duplicate)) + ".")
    return sedi


def verifica(sap: pd.DataFrame, new: pd.DataFrame) -> Verifica:
    """Confronto diretto tra le Sedi estratte da SAP e quelle di New."""
    avvisi: list[str] = []
    sedi_sap = _sedi(sap, "SAP", avvisi)
    sedi_new = _sedi(new, "New", avvisi)

    righe = []
    for sede, descrizione in sedi_sap.items():
        if sede in sedi_new:
            atteso = sedi_new[sede]
            uguale = normalizza_descrizione(descrizione) == normalizza_descrizione(atteso)
            esito = ESITO_ALLINEATA if uguale else esito_descrizione_diversa(atteso)
        elif livello(sede) < LIVELLO_MINIMO:
            esito = ESITO_ESCLUSA
        else:
            esito = ESITO_ECCESSO
        righe.append((sede, descrizione, esito))

    for sede, descrizione in sedi_new.items():                 # mancanti, in fondo
        if sede not in sedi_sap:
            esito = ESITO_ESCLUSA if livello(sede) < LIVELLO_MINIMO else ESITO_MANCANTE
            righe.append((sede, descrizione, esito))

    return Verifica(pd.DataFrame(righe, columns=[COL_SEDE, COL_DESCRIZIONE, COL_ESITO]), avvisi)
