"""Lettura delle liste esportate da SAP negli appunti
(menu Lista > Salva > File > "Negli appunti").

Formato atteso (testo a larghezza fissa):

    13.10.26 Visualizzazione lista dinamica                     1
    ----------------------------------------------------------------
    |  Sede tecnica        |Definizione della sede tecnica  |St.sist.|
    ----------------------------------------------------------------
    |  USE-USS5            |BESS @ Fencepost                |CRT     |

Le colonne vengono individuate dalle posizioni dei "|" nella riga di
intestazione, così che un eventuale "|" contenuto nei dati non sposti le
colonne. Le intestazioni ripetute (cambio pagina) vengono ignorate.

Le funzioni sedi_da_ih06, ordini_da_iw39 e avvisi_da_iw29 convertono le
liste dei layout FL_BESS_MIG, OdM_BESS_MIG e AdM_BESS_MIG nelle colonne
standard usate dal programma.
"""
from __future__ import annotations

import pandas as pd

SEP = "|"

# Colonne standard prodotte
COL_SEDE = "Sede tecnica"
COL_DESCRIZIONE = "Descrizione"
COL_STATO = "Stato"
COL_ORDINE = "Work Order"
COL_AVVISO = "Notification"

# Intestazioni dei layout SAP: {colonna standard: intestazione nel layout}
LAYOUT_IH06 = {COL_SEDE: "Sede tecnica",
               COL_DESCRIZIONE: "Definizione della sede tecnica",
               COL_STATO: "St.sist."}
LAYOUT_IW39 = {COL_ORDINE: "Ordine",
               COL_DESCRIZIONE: "Descrizione",
               COL_SEDE: "Sede tecnica",
               COL_STATO: "Stato sistema"}
LAYOUT_IW29 = {COL_AVVISO: "Avviso",
               COL_DESCRIZIONE: "Descrizione",
               COL_SEDE: "Sede tecnica",
               COL_STATO: "St.sist."}

# Stati di sistema (SAP in lingua italiana) che escludono una Sede tecnica da Actual
STATI_SEDE_ESCLUSI = ("CANC", "OGIN", "FCAN")


class ErroreListaSAP(Exception):
    """Lista esportata da SAP non leggibile o con colonne inattese."""


# ---------------------------------------------------------------------------
# Lettura generica
# ---------------------------------------------------------------------------
def _posizioni_separatori(riga: str) -> list[int]:
    return [i for i, c in enumerate(riga) if c == SEP]


def _dividi(riga: str, posizioni: list[int]) -> list[str] | None:
    """Divisione di una riga dati con le posizioni dell'intestazione;
    in alternativa divisione semplice sul separatore. None se non coerente."""
    if len(riga) >= posizioni[-1] + 1 and all(riga[p] == SEP for p in posizioni):
        return [riga[a + 1:b].strip() for a, b in zip(posizioni, posizioni[1:])]
    parti = riga.strip().split(SEP)
    if len(parti) == len(posizioni) + 1:          # "|a|b|" -> ["", "a", "b", ""]
        return [p.strip() for p in parti[1:-1]]
    return None


def leggi_lista_sap(testo: str) -> pd.DataFrame:
    """Conversione del testo esportato in un DataFrame di sole stringhe.
    Solleva ErroreListaSAP se il testo non contiene una lista riconoscibile."""
    righe = testo.splitlines()
    try:
        indice_intestazione = next(i for i, r in enumerate(righe) if r.startswith(SEP))
    except StopIteration:
        raise ErroreListaSAP("Nessuna lista trovata nel testo esportato da SAP.") from None

    intestazione = righe[indice_intestazione].rstrip()
    posizioni = _posizioni_separatori(intestazione)
    if len(posizioni) < 2:
        raise ErroreListaSAP("Intestazione della lista SAP non riconosciuta.")
    nomi = [intestazione[a + 1:b].strip() for a, b in zip(posizioni, posizioni[1:])]

    dati = []
    for numero, riga in enumerate(righe[indice_intestazione + 1:], start=indice_intestazione + 2):
        riga = riga.rstrip()
        if not riga.startswith(SEP) or riga == intestazione:
            continue                                  # separatori, titoli, intestazioni ripetute
        valori = _dividi(riga, posizioni)
        if valori is None:
            raise ErroreListaSAP(f"Riga {numero} della lista SAP non coerente con l'intestazione.")
        dati.append(valori)

    return pd.DataFrame(dati, columns=nomi, dtype=str)


def seleziona_colonne(df: pd.DataFrame, layout: dict[str, str], nome_lista: str) -> pd.DataFrame:
    """Estrazione e rinomina delle colonne del layout. Errore leggibile se il
    layout SAP non contiene le colonne attese (es. layout modificato)."""
    chiave = {str(c).strip().casefold(): c for c in df.columns}
    mancanti = [v for v in layout.values() if v.casefold() not in chiave]
    if mancanti:
        presenti = ", ".join(f"\"{c}\"" for c in df.columns) or "(nessuna)"
        raise ErroreListaSAP(f"{nome_lista}: colonne non trovate: "
                             + ", ".join(f"\"{c}\"" for c in mancanti)
                             + f". Colonne presenti: {presenti}. Verificare il layout.")
    out = df[[chiave[v.casefold()] for v in layout.values()]].copy()
    out.columns = list(layout.keys())
    return out.reset_index(drop=True)


def contiene_stato(stati: str, stato: str) -> bool:
    """True se lo stato compare tra gli stati di sistema (separati da spazi)."""
    return stato in str(stati).split()


# ---------------------------------------------------------------------------
# Liste specifiche
# ---------------------------------------------------------------------------
def sedi_da_ih06(testo: str, stati_esclusi: tuple[str, ...] = STATI_SEDE_ESCLUSI) -> pd.DataFrame:
    """Sedi tecniche (colonne Sede tecnica, Descrizione) dalla lista IH06,
    escluse quelle il cui stato di sistema contiene uno degli `stati_esclusi`."""
    df = seleziona_colonne(leggi_lista_sap(testo), LAYOUT_IH06, "IH06")
    valide = df[COL_STATO].map(lambda s: not any(contiene_stato(s, e) for e in stati_esclusi))
    return df.loc[valide, [COL_SEDE, COL_DESCRIZIONE]].reset_index(drop=True)


def ordini_da_iw39(testo: str) -> pd.DataFrame:
    """Ordini (Sede tecnica, Work Order, Descrizione, Stato) dalla lista IW39."""
    df = seleziona_colonne(leggi_lista_sap(testo), LAYOUT_IW39, "IW39")
    return df[[COL_SEDE, COL_ORDINE, COL_DESCRIZIONE, COL_STATO]]


def avvisi_da_iw29(testo: str) -> pd.DataFrame:
    """Avvisi (Sede tecnica, Notification, Descrizione, Stato) dalla lista IW29."""
    df = seleziona_colonne(leggi_lista_sap(testo), LAYOUT_IW29, "IW29")
    return df[[COL_SEDE, COL_AVVISO, COL_DESCRIZIONE, COL_STATO]]
