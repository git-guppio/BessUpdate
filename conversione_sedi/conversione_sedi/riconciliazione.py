"""Riconciliazione tra le Sedi tecniche presenti in SAP (Actual) e la nuova
codifica proposta (New).

Per ogni Sede di Actual si determina l'operazione da eseguire in SAP; per ogni
Sede di New si determina se esiste già, se deriva da una Sede di Actual o se va
creata (SPECIFICHE_GUI.md, sezioni 4.3 e 4.4).

Regole principali:
- le Sedi di livello 1 e 2 non vengono mai modificate;
- identità prima della conversione: una Sede di Actual già presente in New
  resta invariata (salvo conflitto con la conversione);
- conversione tramite il nucleo; il codice convertito deve essere presente in New;
- le decisioni manuali hanno sempre la precedenza su quelle automatiche;
- un codice di destinazione è libero solo se nessuna Sede di SAP lo occupa, o
  se la Sede che lo occupa viene a sua volta rinominata (catene ammesse,
  rinomine circolari no);
- più Sedi verso lo stesso codice = conflitto, risolto manualmente;
- vale sempre la descrizione di New.

La conversione resta interamente nel nucleo: questo modulo ne usa i risultati.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd

from conversione_sedi.nucleo import (
    ESITO_DA_VERIFICARE, ESITO_NESSUNA_CORRISPONDENZA, ESITO_OK, Configurazione, converti,
)

COL_SEDE = "Sede tecnica"
COL_DESCRIZIONE = "Descrizione"
LIVELLO_MINIMO = 3                  # i livelli 1 e 2 non vengono mai modificati


# ---------------------------------------------------------------------------
# Valori
# ---------------------------------------------------------------------------
class Operazione(str, Enum):
    """Esito della riconciliazione per una Sede di Actual."""
    ESCLUSA = "Esclusa"                         # livello 1-2
    INVARIATA = "Invariata"
    MODIFICA_DESCRIZIONE = "Modifica descrizione"
    MODIFICA = "Modifica"
    DA_RIMUOVERE = "Da rimuovere"
    MANTENUTA = "Mantenuta"                     # mantenuta per decisione, anche se assente in New
    DA_DECIDERE = "Da decidere"
    DA_VERIFICARE = "Da verificare"
    CONFLITTO = "Conflitto"


class StatoNew(str, Enum):
    """Esito della riconciliazione per una Sede di New."""
    ESCLUSA = "Esclusa"
    ESISTENTE = "Esistente"
    ESISTENTE_DESCRIZIONE = "Esistente - descrizione da modificare"
    DA_MODIFICA = "Ottenuta da modifica"        # deriva dalla modifica di una Sede di Actual
    DA_CREARE = "Da creare"
    IN_SOSPESO = "In sospeso"                   # coinvolta in un conflitto o in una riga da verificare


OPERAZIONI_APERTE = (Operazione.DA_DECIDERE, Operazione.DA_VERIFICARE, Operazione.CONFLITTO)


class TipoDecisione(str, Enum):
    NUOVO_CODICE = "Nuovo codice"
    RIMUOVI = "Da rimuovere"
    MANTIENI = "Mantieni invariata"


@dataclass(frozen=True)
class Decisione:
    """Decisione manuale su una Sede di Actual."""
    tipo: TipoDecisione
    codice: str = ""                            # solo per NUOVO_CODICE

    @staticmethod
    def nuovo_codice(codice: str) -> "Decisione":
        return Decisione(TipoDecisione.NUOVO_CODICE, normalizza_sede(codice))

    @staticmethod
    def rimuovi() -> "Decisione":
        return Decisione(TipoDecisione.RIMUOVI)

    @staticmethod
    def mantieni() -> "Decisione":
        return Decisione(TipoDecisione.MANTIENI)


# ---------------------------------------------------------------------------
# Funzioni di supporto
# ---------------------------------------------------------------------------
def normalizza_sede(valore) -> str:
    if valore is None or (isinstance(valore, float) and pd.isna(valore)):
        return ""
    return str(valore).strip().upper()


_SPAZI = re.compile(r"\s+")


def normalizza_descrizione(valore) -> str:
    """Spazi esterni rimossi e spazi multipli ridotti a uno; maiuscole e ogni
    altro carattere invariati (SPECIFICHE_GUI.md, 4.8)."""
    if valore is None or (isinstance(valore, float) and pd.isna(valore)):
        return ""
    return _SPAZI.sub(" ", str(valore)).strip()


def livello(sede: str) -> int:
    return sede.count("-") + 1


# ---------------------------------------------------------------------------
# Risultato
# ---------------------------------------------------------------------------
@dataclass
class Riconciliazione:
    actual: pd.DataFrame        # vista Check Actual
    new: pd.DataFrame           # vista Check New
    avvisi: list[str] = field(default_factory=list)

    @property
    def righe_aperte(self) -> int:
        return int(self.actual["Operazione"].isin([o.value for o in OPERAZIONI_APERTE]).sum())

    @property
    def completa(self) -> bool:
        """True se ogni Sede ha un'operazione definita: condizione necessaria
        per generare il file della transazione massiva."""
        return self.righe_aperte == 0

    def riepilogo_actual(self) -> dict[str, int]:
        conteggi = self.actual["Operazione"].value_counts()
        return {o.value: int(conteggi.get(o.value, 0)) for o in Operazione}

    def riepilogo_new(self) -> dict[str, int]:
        conteggi = self.new["Stato"].value_counts()
        return {s.value: int(conteggi.get(s.value, 0)) for s in StatoNew}


@dataclass
class _Riga:
    sede: str
    descrizione: str
    codice_out: str | None = None
    esito_conversione: str = ""
    operazione: Operazione = Operazione.DA_DECIDERE
    destinazione: str = ""                     # codice finale (se resta o viene modificata)
    motivo: str = ""
    manuale: bool = False
    sequenza: int | None = None
    codice_conteso: str = ""                   # codice di New conteso (conflitto identità/conversione)

    @property
    def rinomina(self) -> bool:
        return bool(self.destinazione) and self.destinazione != self.sede


# ---------------------------------------------------------------------------
# Lettura degli input
# ---------------------------------------------------------------------------
def _sedi(df: pd.DataFrame, nome: str, avvisi: list[str]) -> dict[str, str]:
    """{sede normalizzata: descrizione}, con avviso per righe duplicate."""
    for col in (COL_SEDE, COL_DESCRIZIONE):
        if col not in df.columns:
            raise KeyError(f"{nome}: colonna \"{col}\" non presente.")
    sedi: dict[str, str] = {}
    duplicate: list[str] = []
    for s, d in zip(df[COL_SEDE], df[COL_DESCRIZIONE]):
        s = normalizza_sede(s)
        if not s:
            continue
        if s in sedi:
            duplicate.append(s)
            continue
        sedi[s] = "" if d is None or (isinstance(d, float) and pd.isna(d)) else str(d)
    if duplicate:
        avvisi.append(f"{nome}: Sedi tecniche duplicate ignorate (vale la prima): "
                      + ", ".join(sorted(set(duplicate))) + ".")
    return sedi


# ---------------------------------------------------------------------------
# Riconciliazione
# ---------------------------------------------------------------------------
def riconcilia(actual: pd.DataFrame, new: pd.DataFrame, conf: Configurazione,
               decisioni: dict[str, Decisione] | None = None) -> Riconciliazione:
    """Riconciliazione di Actual con New. `decisioni` associa a una Sede di
    Actual una decisione manuale, che ha la precedenza su quella automatica."""
    avvisi: list[str] = []
    sedi_actual = _sedi(actual, "Actual", avvisi)
    sedi_new = _sedi(new, "New", avvisi)
    decisioni = {normalizza_sede(k): v for k, v in (decisioni or {}).items()}

    orfane = sorted(k for k in decisioni if k not in sedi_actual)
    if orfane:
        avvisi.append("Decisioni manuali su Sedi non più presenti in Actual (orfane): "
                      + ", ".join(orfane) + ".")

    righe = [_riga_iniziale(s, d, sedi_new, conf, decisioni.get(s)) for s, d in sedi_actual.items()]
    per_sede = {r.sede: r for r in righe}
    in_sospeso = _risolvi_destinazioni(righe, per_sede)
    in_sospeso |= {r.codice_conteso for r in righe if r.codice_conteso}
    _descrizioni(righe, sedi_new)
    _sequenza(righe, per_sede)

    return Riconciliazione(_vista_actual(righe, sedi_new),
                           _vista_new(righe, sedi_new, in_sospeso), avvisi)


def _riga_iniziale(sede: str, descrizione: str, sedi_new: dict[str, str],
                   conf: Configurazione, decisione: Decisione | None) -> _Riga:
    r = _Riga(sede, descrizione)
    if livello(sede) < LIVELLO_MINIMO:
        r.operazione, r.motivo = Operazione.ESCLUSA, "Livello 1 o 2: mai modificato."
        r.destinazione = sede                   # il codice resta occupato
        return r

    conv = converti(sede, conf)
    r.codice_out, r.esito_conversione = conv.codice_out, conv.esito
    convertita = conv.nuova_sede_tecnica if conv.esito == ESITO_OK else None

    if decisione is not None:
        r.manuale = True
        if decisione.tipo == TipoDecisione.RIMUOVI:
            if sede in sedi_new:
                r.operazione = Operazione.DA_VERIFICARE
                r.motivo = "Sede presente in New: la rimozione non è coerente."
                r.destinazione = sede
            else:
                r.operazione, r.motivo = Operazione.DA_RIMUOVERE, "Decisione manuale."
                r.destinazione = ""
            return r
        if decisione.tipo == TipoDecisione.MANTIENI:
            r.operazione = Operazione.INVARIATA if sede in sedi_new else Operazione.MANTENUTA
            r.motivo, r.destinazione = "Decisione manuale.", sede
            return r
        # NUOVO_CODICE
        if decisione.codice not in sedi_new:
            r.operazione = Operazione.DA_VERIFICARE
            r.motivo = f"Codice inserito a mano {decisione.codice or '(vuoto)'} assente in New."
            r.destinazione = sede               # finché non è risolta, la Sede resta dov'è
            return r
        r.destinazione, r.motivo = decisione.codice, "Codice inserito a mano."
        r.operazione = Operazione.MODIFICA if r.rinomina else Operazione.INVARIATA
        return r

    # identità prima della conversione
    if sede in sedi_new:
        r.destinazione = sede
        if convertita and convertita != sede and convertita in sedi_new:
            r.operazione = Operazione.CONFLITTO
            r.motivo = (f"Presente in New, ma la conversione darebbe {convertita}, "
                        "anch'essa presente in New.")
            r.codice_conteso = convertita
        else:
            r.operazione, r.motivo = Operazione.INVARIATA, "Presente in New."
        return r

    if conv.esito == ESITO_NESSUNA_CORRISPONDENZA:
        r.operazione = Operazione.DA_DECIDERE
        r.motivo = "Nessuna regola di conversione: decidere se rimuoverla, mantenerla o assegnare un nuovo codice."
        r.destinazione = sede
    elif conv.esito == ESITO_DA_VERIFICARE:
        r.operazione = Operazione.DA_VERIFICARE
        r.motivo = f"Conversione da verificare: {conv.nuova_sede_tecnica}."
        r.destinazione = sede
    elif convertita not in sedi_new:
        r.operazione = Operazione.DA_VERIFICARE
        r.motivo = f"Codice convertito {convertita} assente in New."
        r.destinazione = sede
    else:
        r.operazione, r.motivo = Operazione.MODIFICA, "Conversione automatica."
        r.destinazione = convertita
    return r


def _risolvi_destinazioni(righe: list[_Riga], per_sede: dict[str, _Riga]) -> set[str]:
    """Individuazione dei conflitti sui codici di destinazione. Restituisce i
    codici di New coinvolti in conflitti (stato In sospeso)."""
    in_sospeso: set[str] = set()

    def in_conflitto(r: _Riga, motivo: str) -> bool:
        if r.operazione == Operazione.CONFLITTO:
            return False
        r.operazione, r.motivo = Operazione.CONFLITTO, motivo
        return True

    # 1) più Sedi verso lo stesso codice (comprese quelle che lo occupano già)
    richieste: dict[str, list[_Riga]] = {}
    for r in righe:
        if r.destinazione and r.operazione not in (Operazione.DA_DECIDERE, Operazione.DA_VERIFICARE):
            richieste.setdefault(r.destinazione, []).append(r)
    for codice, gruppo in richieste.items():
        if len(gruppo) > 1:
            in_sospeso.add(codice)
            nomi = ", ".join(g.sede for g in gruppo)
            for g in gruppo:
                in_conflitto(g, f"Più Sedi verso lo stesso codice {codice}: {nomi}.")

    # 2) rinomine circolari (A -> B, B -> A)
    for r in righe:
        if r.operazione != Operazione.MODIFICA:
            continue
        visti, corrente = [r.sede], r
        while True:
            succ = per_sede.get(corrente.destinazione)
            if succ is None or succ.operazione != Operazione.MODIFICA:
                break
            if succ.sede == r.sede:
                ciclo = " -> ".join(visti + [r.sede])
                for s in visti:
                    in_sospeso.add(per_sede[s].destinazione)
                    in_conflitto(per_sede[s], f"Rinomina circolare: {ciclo}.")
                break
            if succ.sede in visti:
                break
            visti.append(succ.sede)
            corrente = succ

    # 3) codice occupato in SAP da una Sede che non viene rinominata
    #    (ripetuto finché ci sono cambiamenti, per propagare lungo le catene)
    cambiato = True
    while cambiato:
        cambiato = False
        for r in righe:
            if r.operazione != Operazione.MODIFICA or not r.rinomina:
                continue
            occupante = per_sede.get(r.destinazione)
            if occupante is None:
                continue
            if occupante.operazione != Operazione.MODIFICA or not occupante.rinomina:
                in_sospeso.add(r.destinazione)
                cambiato |= in_conflitto(r, f"Il codice {r.destinazione} è occupato in SAP da "
                                            f"{occupante.sede} ({occupante.operazione.value}).")

    return in_sospeso


def _descrizioni(righe: list[_Riga], sedi_new: dict[str, str]) -> None:
    for r in righe:
        if r.operazione == Operazione.INVARIATA and r.destinazione in sedi_new:
            if normalizza_descrizione(r.descrizione) != normalizza_descrizione(sedi_new[r.destinazione]):
                r.operazione = Operazione.MODIFICA_DESCRIZIONE


def _sequenza(righe: list[_Riga], per_sede: dict[str, _Riga]) -> None:
    """Ordine di esecuzione delle modifiche di codice: se A -> B e B -> C,
    B va rinominata prima di A."""
    modifiche = [r for r in righe if r.operazione == Operazione.MODIFICA]
    numero = 0

    def assegna(r: _Riga) -> None:
        nonlocal numero
        if r.sequenza is not None:
            return
        occupante = per_sede.get(r.destinazione)
        if occupante is not None and occupante.operazione == Operazione.MODIFICA:
            assegna(occupante)
        numero += 1
        r.sequenza = numero

    for r in sorted(modifiche, key=lambda r: r.sede):
        assegna(r)


# ---------------------------------------------------------------------------
# Viste
# ---------------------------------------------------------------------------
COLONNE_ACTUAL = ("Sede tecnica", "Descrizione", "Codice_Out", "Esito conversione",
                  "Nuova sede tecnica", "Nuova descrizione", "Operazione", "Motivo",
                  "Decisione manuale", "Sequenza")
COLONNE_NEW = ("Sede tecnica", "Descrizione", "Stato", "Sede di provenienza")


def _vista_actual(righe: list[_Riga], sedi_new: dict[str, str]) -> pd.DataFrame:
    dati = []
    for r in righe:
        definita = r.operazione in (Operazione.INVARIATA, Operazione.MODIFICA_DESCRIZIONE,
                                    Operazione.MODIFICA)
        dati.append({
            "Sede tecnica": r.sede,
            "Descrizione": r.descrizione,
            "Codice_Out": r.codice_out,
            "Esito conversione": r.esito_conversione,
            "Nuova sede tecnica": r.destinazione if definita else None,
            "Nuova descrizione": sedi_new.get(r.destinazione) if definita else None,
            "Operazione": r.operazione.value,
            "Motivo": r.motivo,
            "Decisione manuale": "Sì" if r.manuale else "",
            "Sequenza": r.sequenza,
        })
    df = pd.DataFrame(dati, columns=list(COLONNE_ACTUAL))
    df["Sequenza"] = df["Sequenza"].astype("Int64")
    return df


def _vista_new(righe: list[_Riga], sedi_new: dict[str, str], in_sospeso: set[str]) -> pd.DataFrame:
    attuale = {r.sede: r for r in righe}
    provenienza = {r.destinazione: r for r in righe
                   if r.operazione == Operazione.MODIFICA}
    dati = []
    for sede, descrizione in sedi_new.items():
        origine = ""
        if livello(sede) < LIVELLO_MINIMO:
            stato = StatoNew.ESCLUSA
        elif sede in in_sospeso:
            stato = StatoNew.IN_SOSPESO
        elif sede in provenienza:
            stato, origine = StatoNew.DA_MODIFICA, provenienza[sede].sede
        elif sede in attuale:
            r = attuale[sede]
            if r.operazione == Operazione.INVARIATA:
                stato = StatoNew.ESISTENTE
            elif r.operazione == Operazione.MODIFICA_DESCRIZIONE:
                stato = StatoNew.ESISTENTE_DESCRIZIONE
            else:
                stato = StatoNew.IN_SOSPESO     # esiste in SAP ma la sua Sede è ancora aperta
        else:
            stato = StatoNew.DA_CREARE
        dati.append({"Sede tecnica": sede, "Descrizione": descrizione,
                     "Stato": stato.value, "Sede di provenienza": origine})
    return pd.DataFrame(dati, columns=list(COLONNE_NEW))
