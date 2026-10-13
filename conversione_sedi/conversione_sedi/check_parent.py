"""Check Parent: verifica della gerarchia delle Sedi tecniche nello stato
finale, cioè la struttura che esisterà in SAP dopo il caricamento
(SPECIFICHE_GUI.md, sezione 4.5).

- stato_finale(ric)        -> Sedi dello stato finale ricavate dalla riconciliazione
- verifica_gerarchia(df)   -> controllo di duplicati e parent su una tabella
                              (anche modificata a mano)

Regole:
- il parent di una Sede è la Sede senza l'ultimo segmento;
- si verifica solo il parent diretto: un buco nella gerarchia viene
  segnalato una sola volta, sulla riga del figlio diretto;
- la radice (livello 1) si considera sempre esistente;
- prima si cercano i duplicati, poi i parent mancanti; più errori sulla
  stessa riga vengono riportati insieme, separati da " | ".
"""
from __future__ import annotations

import pandas as pd

from conversione_sedi.riconciliazione import Operazione, Riconciliazione, StatoNew, livello, normalizza_sede

COL_SEDE = "Nuove sedi tecniche"
COL_ORIGINE = "Origine"
COL_CHECK = "Check"

CHECK_OK = "OK"
CHECK_DUPLICATO = "Valore duplicato"
CHECK_PARENT = "Parent NOK"
CHECK_VUOTA = "Sede vuota"
SEP_ERRORI = " | "

# Origine delle Sedi nello stato finale
ORIGINE_ESISTENTE = "Esistente"
ORIGINE_MODIFICA = "Modifica da {}"
ORIGINE_CREAZIONE = "Da creare"
ORIGINE_MANTENUTA = "Mantenuta"
ORIGINE_PROVVISORIA = "Provvisoria ({})"

_ESISTENTI = (Operazione.ESCLUSA, Operazione.INVARIATA, Operazione.MODIFICA_DESCRIZIONE)
_APERTE = (Operazione.DA_DECIDERE, Operazione.DA_VERIFICARE, Operazione.CONFLITTO)


def parent(sede: str) -> str:
    """Sede senza l'ultimo segmento ("" per la radice)."""
    return sede.rsplit("-", 1)[0] if "-" in sede else ""


def stato_finale(ric: Riconciliazione) -> pd.DataFrame:
    """Sedi tecniche che esisteranno in SAP dopo il caricamento:
    invariate, modificate, mantenute e da creare; escluse quelle da rimuovere.
    Le Sedi ancora da risolvere entrano con il codice attuale, come provvisorie."""
    righe: list[tuple[str, str]] = []
    for _, r in ric.actual.iterrows():
        operazione = Operazione(r["Operazione"])
        if operazione in _ESISTENTI:
            righe.append((r["Sede tecnica"], ORIGINE_ESISTENTE))
        elif operazione == Operazione.MODIFICA:
            righe.append((r["Nuova sede tecnica"], ORIGINE_MODIFICA.format(r["Sede tecnica"])))
        elif operazione == Operazione.MANTENUTA:
            righe.append((r["Sede tecnica"], ORIGINE_MANTENUTA))
        elif operazione in _APERTE:
            righe.append((r["Sede tecnica"], ORIGINE_PROVVISORIA.format(operazione.value)))
        # DA_RIMUOVERE: non fa parte dello stato finale
    for sede in ric.new.loc[ric.new["Stato"] == StatoNew.DA_CREARE.value, "Sede tecnica"]:
        righe.append((sede, ORIGINE_CREAZIONE))

    df = pd.DataFrame(righe, columns=[COL_SEDE, COL_ORIGINE])
    return df.sort_values(COL_SEDE, kind="stable").reset_index(drop=True)


def verifica_gerarchia(df: pd.DataFrame, colonna: str = COL_SEDE) -> pd.DataFrame:
    """Copia di df con la colonna Check: "OK", "Valore duplicato",
    "Parent NOK (manca <parent>)" o "Sede vuota"."""
    if colonna not in df.columns:
        raise KeyError(f"Colonna \"{colonna}\" non presente.")
    sedi = [normalizza_sede(s) for s in df[colonna]]
    presenti = {s for s in sedi if s}
    conteggi = pd.Series([s for s in sedi if s], dtype=str).value_counts()

    esiti = []
    for sede in sedi:
        if not sede:
            esiti.append(CHECK_VUOTA)
            continue
        errori = []
        if conteggi.get(sede, 0) > 1:
            errori.append(CHECK_DUPLICATO)
        p = parent(sede)
        if p and livello(p) > 1 and p not in presenti:     # la radice esiste sempre
            errori.append(f"{CHECK_PARENT} (manca {p})")
        esiti.append(SEP_ERRORI.join(errori) if errori else CHECK_OK)

    out = df.copy()
    out[COL_CHECK] = esiti
    return out


def riepilogo(df_verificato: pd.DataFrame) -> dict[str, int]:
    """Conteggio delle righe corrette e degli errori (una riga può avere più errori)."""
    check = df_verificato[COL_CHECK]
    return {
        CHECK_OK: int((check == CHECK_OK).sum()),
        CHECK_DUPLICATO: int(check.str.contains(CHECK_DUPLICATO, regex=False).sum()),
        CHECK_PARENT: int(check.str.contains(CHECK_PARENT, regex=False).sum()),
        CHECK_VUOTA: int((check == CHECK_VUOTA).sum()),
    }
