"""Caricamento della nuova codifica (tab New) da file Excel o CSV, con i
controlli bloccanti di SPECIFICHE_GUI.md, sezioni 3.2 e 4.1:

- presenza delle colonne "Sede tecnica" e "Descrizione" (individuate per nome
  dell'intestazione, senza distinzione tra maiuscole e minuscole, spazi e "_");
- nessuna Sede tecnica duplicata;
- impianto unico: tutte le Sedi hanno gli stessi primi due livelli.

In caso di errore viene sollevata ErroreDati con l'elenco dei problemi e dei
numeri di riga del file (riga 1 = intestazione).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from conversione_sedi.ingresso_uscita import ErroreDati, leggi_sedi
from conversione_sedi.riconciliazione import livello, normalizza_sede

COL_SEDE = "Sede tecnica"
COL_DESCRIZIONE = "Descrizione"
MAX_RIGHE_ELENCATE = 20


@dataclass
class NuovaCodifica:
    dati: pd.DataFrame                  # colonne Sede tecnica, Descrizione
    impianto: str                       # es. "USE-USS5"
    avvisi: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Impianto
# ---------------------------------------------------------------------------
def impianto_di(sede: str) -> str:
    """Primi due livelli della Sede tecnica ("" se di livello 1)."""
    parti = sede.split("-")
    return "-".join(parti[:2]) if len(parti) >= 2 else ""


def appartiene(sede: str, impianto: str) -> bool:
    """True se la Sede appartiene all'impianto (compresa la radice di livello 1)."""
    if livello(sede) == 1:
        return sede == impianto.split("-")[0]
    return impianto_di(sede) == impianto


def impianto_prevalente(sedi: list[str]) -> str:
    """Impianto più frequente tra le Sedi di livello >= 2 ("" se nessuna)."""
    conteggi = Counter(impianto_di(s) for s in sedi if livello(s) >= 2)
    return conteggi.most_common(1)[0][0] if conteggi else ""


def _elenco(voci: list[str]) -> list[str]:
    if len(voci) <= MAX_RIGHE_ELENCATE:
        return voci
    return voci[:MAX_RIGHE_ELENCATE] + [f"... e altre {len(voci) - MAX_RIGHE_ELENCATE}."]


def verifica_impianto(sedi: list[str], righe: list[int] | None = None,
                      impianto: str | None = None) -> tuple[str, list[str]]:
    """Controllo dell'impianto unico. Restituisce (impianto, errori).
    Se `impianto` non è indicato si usa quello prevalente."""
    righe = righe or list(range(1, len(sedi) + 1))
    impianto = impianto or impianto_prevalente(sedi)
    if not impianto:
        return "", ["Impossibile determinare l'impianto: nessuna Sede tecnica di livello 2 o superiore."]
    diverse = [f"Riga {n}: {s} non appartiene all'impianto {impianto}."
               for s, n in zip(sedi, righe) if not appartiene(s, impianto)]
    return impianto, _elenco(diverse)


# ---------------------------------------------------------------------------
# Caricamento
# ---------------------------------------------------------------------------
def _chiave(nome) -> str:
    return str(nome).strip().casefold().replace("_", " ")


def _colonna(df: pd.DataFrame, nome: str) -> str | None:
    trovate = [c for c in df.columns if _chiave(c) == _chiave(nome)]
    return trovate[0] if len(trovate) == 1 else None


def valida_new(df: pd.DataFrame, nome_file: str = "New") -> NuovaCodifica:
    """Controllo e normalizzazione di una tabella New già letta."""
    colonne = {nome: _colonna(df, nome) for nome in (COL_SEDE, COL_DESCRIZIONE)}
    mancanti = [n for n, c in colonne.items() if c is None]
    if mancanti:
        presenti = ", ".join(f"\"{c}\"" for c in df.columns) or "(nessuna)"
        raise ErroreDati([f"{nome_file}: colonna \"{n}\" mancante o ripetuta." for n in mancanti]
                         + [f"Colonne presenti: {presenti}."])

    sedi, descrizioni, righe, senza_sede = [], [], [], []
    for indice, (s, d) in enumerate(zip(df[colonne[COL_SEDE]], df[colonne[COL_DESCRIZIONE]])):
        riga = indice + 2                               # riga 1 = intestazione
        s = normalizza_sede(s)
        d = "" if d is None or (isinstance(d, float) and pd.isna(d)) else str(d).strip()
        if not s:
            if d:
                senza_sede.append(riga)
            continue                                    # righe vuote ignorate
        sedi.append(s)
        descrizioni.append(d)
        righe.append(riga)

    if not sedi:
        raise ErroreDati([f"{nome_file}: nessuna Sede tecnica presente."])

    errori: list[str] = []
    posizioni: dict[str, list[int]] = {}
    for s, n in zip(sedi, righe):
        posizioni.setdefault(s, []).append(n)
    duplicate = [f"{s} ripetuta alle righe {', '.join(map(str, n))}."
                 for s, n in posizioni.items() if len(n) > 1]
    if duplicate:
        errori.append(f"{nome_file}: Sedi tecniche duplicate:")
        errori.extend(_elenco(duplicate))

    impianto, diverse = verifica_impianto(sedi, righe)
    if diverse:
        errori.append(f"{nome_file}: la lista deve riguardare un solo impianto:")
        errori.extend(diverse)
    if errori:
        raise ErroreDati(errori)

    avvisi = []
    if senza_sede:
        avvisi.append(f"{nome_file}: righe con descrizione ma senza Sede tecnica, ignorate: "
                      + ", ".join(map(str, senza_sede[:MAX_RIGHE_ELENCATE]))
                      + (" ..." if len(senza_sede) > MAX_RIGHE_ELENCATE else "") + ".")
    dati = pd.DataFrame({COL_SEDE: sedi, COL_DESCRIZIONE: descrizioni}, dtype=str)
    return NuovaCodifica(dati, impianto, avvisi)


def carica_new(percorso: str | Path, foglio: str | None = None) -> NuovaCodifica:
    """Lettura e controllo del file della nuova codifica."""
    percorso = Path(percorso)
    return valida_new(leggi_sedi(percorso, foglio), percorso.name)
