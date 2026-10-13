"""Modello del progetto: stato completo del lavoro su un impianto.

Contiene le tabelle (New, Actual, No_Wo, Check Parent, dati SAP della scheda
Check) con le relative modifiche manuali, le decisioni della riconciliazione e
le date delle estrazioni SAP; calcola le schede derivate e il loro stato
(SPECIFICHE_GUI.md, sezione 3.1):

    New ──► Actual ──► FL da creare / Check New / Check Actual ──► Check Parent
                                         └──► No_Wo (a riconciliazione completa)
    New ──► Check

- i calcoli locali vengono rifatti automaticamente quando cambiano i dati;
- le estrazioni SAP non vengono mai ripetute automaticamente: la scheda passa
  a "Da aggiornare" quando i dati da cui dipende sono cambiati;
- il progetto viene salvato automaticamente (file .bessprj, JSON compresso)
  dopo ogni modifica, se ha un percorso.

Il modello non dipende dall'interfaccia grafica né da SAP: riceve i dati già
estratti (sap.py) o letti da file (nuova_codifica.py).
"""
from __future__ import annotations

import gzip
import json
import os
from contextlib import contextmanager
from datetime import datetime
from enum import Enum
from pathlib import Path

import pandas as pd

from conversione_sedi.check_parent import (
    COL_CHECK, COL_PROVENIENZA, COL_SEDE as COL_NUOVE_SEDI, stato_finale, verifica_gerarchia,
)
from conversione_sedi.ingresso_uscita import REGOLE_PREDEFINITE, TRASFORMAZIONI_PREDEFINITE
from conversione_sedi.nucleo import carica_configurazione, elabora_dataframe
from conversione_sedi.nuova_codifica import NuovaCodifica, appartiene
from conversione_sedi.riconciliazione import (
    Decisione, Operazione, Riconciliazione, TipoDecisione, normalizza_sede, riconcilia,
)
from conversione_sedi.tabella import MetaRiga, Tabella
from conversione_sedi.verifica import Verifica, verifica

ESTENSIONE = ".bessprj"
FORMATO = 1
MAX_ERRORI = 20

COLONNE_SEDI = ("Sede tecnica", "Descrizione")
COLONNE_NO_WO = ("Sede tecnica", "Work Order", "Notification", "Descrizione", "Stato")
COLONNE_CHECK_PARENT = (COL_NUOVE_SEDI, COL_PROVENIENZA)
COLONNE_FL_DA_CREARE = ("Sede tecnica", "Descrizione", "Codice_Out", "Nuove sedi tecniche", "Esito")


class Scheda(str, Enum):
    NEW = "New"
    ACTUAL = "Actual"
    FL_DA_CREARE = "FL da creare"
    CHECK_NEW = "Check New"
    CHECK_ACTUAL = "Check Actual"
    CHECK_PARENT = "Check Parent"
    NO_WO = "No_Wo"
    CHECK = "Check"


class StatoScheda(str, Enum):
    BLOCCATA = "Bloccata"               # passaggi precedenti non eseguiti
    DA_ESEGUIRE = "Da eseguire"         # disponibile, mai eseguita
    AGGIORNATA = "Aggiornata"
    DA_AGGIORNARE = "Da aggiornare"     # estrazione SAP basata su dati cambiati


class ErroreProgetto(Exception):
    """Operazione non ammessa sul progetto (messaggio per l'utente)."""


class ImpiantoDiverso(ErroreProgetto):
    """Il file New riguarda un impianto diverso da quello del progetto."""

    def __init__(self, attuale: str, nuovo: str):
        self.attuale, self.nuovo = attuale, nuovo
        super().__init__(f"Il file riguarda l'impianto {nuovo}, il progetto l'impianto {attuale}.")


# ---------------------------------------------------------------------------
# Impostazioni dell'utente (ultimo progetto aperto)
# ---------------------------------------------------------------------------
def cartella_impostazioni() -> Path:
    return Path(os.environ.get("APPDATA") or Path.home()) / "BESS_Update"


def _file_impostazioni() -> Path:
    return cartella_impostazioni() / "impostazioni.json"


def ultimo_progetto() -> Path | None:
    try:
        percorso = json.loads(_file_impostazioni().read_text(encoding="utf-8")).get("ultimo_progetto")
    except (OSError, ValueError):
        return None
    return Path(percorso) if percorso and Path(percorso).is_file() else None


def ricorda_progetto(percorso: Path) -> None:
    try:
        _file_impostazioni().parent.mkdir(parents=True, exist_ok=True)
        _file_impostazioni().write_text(json.dumps({"ultimo_progetto": str(percorso)}), encoding="utf-8")
    except OSError:
        pass                                    # non bloccante


# ---------------------------------------------------------------------------
# Progetto
# ---------------------------------------------------------------------------
class Progetto:
    def __init__(self, regole: str | Path = REGOLE_PREDEFINITE,
                 trasformazioni: str | Path = TRASFORMAZIONI_PREDEFINITE):
        self.regole, self.trasformazioni = Path(regole), Path(trasformazioni)
        self.conf = carica_configurazione(self.regole, self.trasformazioni)
        self.percorso: Path | None = None
        self.salvataggio_automatico = True
        self._sospeso = 0
        self._da_salvare = False
        self._cache: dict[str, tuple] = {}
        self._inizializza()

    def _inizializza(self) -> None:
        sede = {"Sede tecnica": normalizza_sede}
        self.impianto = ""
        self.avvisi_new: list[str] = []
        self.new = Tabella(COLONNE_SEDI, normalizza=sede, valida=self._valida_impianto,
                           notifica=self._modificato)
        self.actual = Tabella(COLONNE_SEDI, normalizza=sede, valida=self._valida_impianto,
                              notifica=self._modificato)
        self.check_sap = Tabella(COLONNE_SEDI, normalizza=sede, valida=self._valida_impianto,
                                 notifica=self._modificato)
        self.no_wo = Tabella(COLONNE_NO_WO, chiave=("Work Order", "Notification"),
                             normalizza=sede, notifica=self._modificato)
        self.check_parent = Tabella(COLONNE_CHECK_PARENT, normalizza={COL_NUOVE_SEDI: normalizza_sede},
                                    valida=self._valida_impianto_cp, notifica=self._modificato)
        self.decisioni: dict[str, Decisione] = {}
        self._versione_decisioni = 0
        self.estrazioni: dict[str, datetime | None] = {"actual": None, "no_wo": None, "check": None}
        self.sedi_no_wo: tuple[str, ...] = ()
        self._cache.clear()

    # ------------------------------------------------------------------
    # Validazione
    # ------------------------------------------------------------------
    def _valida_impianto(self, valori: dict[str, str]) -> list[str]:
        sede = valori.get("Sede tecnica", "")
        if self.impianto and sede and not appartiene(sede, self.impianto):
            return [f"{sede} non appartiene all'impianto {self.impianto}."]
        return []

    def _valida_impianto_cp(self, valori: dict[str, str]) -> list[str]:
        return self._valida_impianto({"Sede tecnica": valori.get(COL_NUOVE_SEDI, "")})

    def _controlla_impianto(self, df: pd.DataFrame, nome: str) -> None:
        if not self.impianto:
            raise ErroreProgetto("Caricare prima la nuova codifica (New).")
        estranee = [s for s in (normalizza_sede(v) for v in df["Sede tecnica"])
                    if s and not appartiene(s, self.impianto)]
        if estranee:
            elenco = ", ".join(estranee[:MAX_ERRORI]) + (" ..." if len(estranee) > MAX_ERRORI else "")
            raise ErroreProgetto(f"{nome}: Sedi tecniche di un impianto diverso da {self.impianto}: {elenco}")

    # ------------------------------------------------------------------
    # Salvataggio automatico
    # ------------------------------------------------------------------
    def _modificato(self) -> None:
        if self._sospeso:
            self._da_salvare = True
        elif self.percorso and self.salvataggio_automatico:
            self.salva()

    @contextmanager
    def _operazione(self):
        """Più modifiche con un solo salvataggio finale."""
        self._sospeso += 1
        try:
            yield
        finally:
            self._sospeso -= 1
            if not self._sospeso and self._da_salvare:
                self._da_salvare = False
                self._modificato()

    def _ha_dati(self) -> bool:
        return not (self.new.vuota and self.actual.vuota and self.check_sap.vuota and self.no_wo.vuota)

    # ------------------------------------------------------------------
    # Dati in ingresso
    # ------------------------------------------------------------------
    def imposta_new(self, nc: NuovaCodifica, conserva_modifiche: bool = True, azzera: bool = False) -> None:
        """Caricamento della nuova codifica. Con un impianto diverso solleva
        ImpiantoDiverso, a meno che azzera=True (tutto il lavoro viene scartato)."""
        with self._operazione():
            if self.impianto and nc.impianto != self.impianto and self._ha_dati():
                if not azzera:
                    raise ImpiantoDiverso(self.impianto, nc.impianto)
                self._inizializza()
            self.impianto = nc.impianto
            self.avvisi_new = list(nc.avvisi)
            self.new.imposta_base(nc.dati, conserva_modifiche)

    def imposta_actual(self, df: pd.DataFrame, conserva_modifiche: bool = True,
                       quando: datetime | None = None) -> None:
        """Dati estratti da SAP (IH06). Scartando le modifiche manuali vengono
        scartate anche le decisioni della riconciliazione."""
        self._controlla_impianto(df, "Actual")
        with self._operazione():
            self.actual.imposta_base(df, conserva_modifiche)
            if not conserva_modifiche and self.decisioni:
                self.decisioni.clear()
                self._versione_decisioni += 1
            self.estrazioni["actual"] = quando or datetime.now()

    def imposta_check_sap(self, df: pd.DataFrame, conserva_modifiche: bool = True,
                          quando: datetime | None = None) -> None:
        """Dati estratti da SAP (IH06) per la verifica dopo il caricamento."""
        self._controlla_impianto(df, "Check")
        with self._operazione():
            self.check_sap.imposta_base(df, conserva_modifiche)
            self.estrazioni["check"] = quando or datetime.now()

    def imposta_no_wo(self, ordini: pd.DataFrame, avvisi: pd.DataFrame, sedi: list[str],
                      conserva_modifiche: bool = True, quando: datetime | None = None) -> None:
        """Ordini (IW39) e avvisi (IW29) estratti per le Sedi indicate."""
        righe = [{"Sede tecnica": r["Sede tecnica"], "Work Order": r["Work Order"], "Notification": "",
                  "Descrizione": r["Descrizione"], "Stato": r["Stato"]} for _, r in ordini.iterrows()]
        righe += [{"Sede tecnica": r["Sede tecnica"], "Work Order": "", "Notification": r["Notification"],
                   "Descrizione": r["Descrizione"], "Stato": r["Stato"]} for _, r in avvisi.iterrows()]
        with self._operazione():
            self.no_wo.imposta_base(pd.DataFrame(righe, columns=list(COLONNE_NO_WO)), conserva_modifiche)
            self.sedi_no_wo = tuple(sorted({normalizza_sede(s) for s in sedi if normalizza_sede(s)}))
            self.estrazioni["no_wo"] = quando or datetime.now()

    def conta_modifiche_manuali(self, scheda: Scheda) -> int:
        """Modifiche che una nuova importazione/estrazione potrebbe scartare."""
        if scheda == Scheda.NEW:
            return self.new.conta_modifiche()
        if scheda == Scheda.ACTUAL:
            return self.actual.conta_modifiche() + len(self.decisioni)
        if scheda == Scheda.NO_WO:
            return self.no_wo.conta_modifiche()
        if scheda == Scheda.CHECK:
            return self.check_sap.conta_modifiche()
        return 0

    # ------------------------------------------------------------------
    # Decisioni della riconciliazione
    # ------------------------------------------------------------------
    def imposta_decisione(self, sede: str, decisione: Decisione | None) -> None:
        """Decisione manuale su una Sede di Actual (None = torna all'automatico)."""
        sede = normalizza_sede(sede)
        if decisione is None:
            if self.decisioni.pop(sede, None) is None:
                return
        else:
            self.decisioni[sede] = decisione
        self._versione_decisioni += 1
        self._modificato()

    def risolvi_conflitto(self, vincitrice: str, altre: list[str]) -> None:
        """La Sede vincitrice segue la regola automatica; le altre vengono rimosse."""
        with self._operazione():
            self.imposta_decisione(vincitrice, None)
            for sede in altre:
                if normalizza_sede(sede) != normalizza_sede(vincitrice):
                    self.imposta_decisione(sede, Decisione.rimuovi())

    # ------------------------------------------------------------------
    # Schede derivate (ricalcolate automaticamente)
    # ------------------------------------------------------------------
    def _calcola(self, nome: str, chiave: tuple, funzione):
        precedente = self._cache.get(nome)
        if precedente is None or precedente[0] != chiave:
            self._cache[nome] = (chiave, funzione())
        return self._cache[nome][1]

    def fl_da_creare(self) -> pd.DataFrame | None:
        if self.stato(Scheda.FL_DA_CREARE) == StatoScheda.BLOCCATA:
            return None

        def calcola():
            out = elabora_dataframe(self.actual.dati(), self.conf, "Sede tecnica")
            out = out.rename(columns={"Nuova_Sede_Tecnica": "Nuove sedi tecniche"})
            return out[list(COLONNE_FL_DA_CREARE)]
        return self._calcola("fl", (self.actual.versione,), calcola)

    def riconciliazione(self) -> Riconciliazione | None:
        if self.stato(Scheda.CHECK_ACTUAL) == StatoScheda.BLOCCATA:
            return None
        return self._calcola(
            "ric", (self.new.versione, self.actual.versione, self._versione_decisioni),
            lambda: riconcilia(self.actual.dati(), self.new.dati(), self.conf, self.decisioni))

    def check_parent_vista(self) -> tuple[pd.DataFrame, list[MetaRiga]] | None:
        """Tabella Check Parent (stato finale + modifiche manuali) con la colonna Check."""
        ric = self.riconciliazione()
        if ric is None:
            return None
        chiave_base = (self.new.versione, self.actual.versione, self._versione_decisioni)
        if self._cache.get("cp_base") != chiave_base:
            notifica, self.check_parent.notifica = self.check_parent.notifica, None
            try:                                    # dato calcolato: nessun salvataggio
                self.check_parent.imposta_base(stato_finale(ric), conserva_modifiche=True)
            finally:
                self.check_parent.notifica = notifica
            self._cache["cp_base"] = chiave_base

        vista, meta = self.check_parent.vista()
        verificata = verifica_gerarchia(self.check_parent.dati())
        esiti = dict(zip(verificata[COL_NUOVE_SEDI], verificata[COL_CHECK]))
        vista.insert(1, COL_CHECK, ["" if m.rimossa else esiti.get(s, "")
                                    for s, m in zip(vista[COL_NUOVE_SEDI], meta)])
        return vista, meta

    def verifica(self) -> Verifica | None:
        if self.stato(Scheda.CHECK) in (StatoScheda.BLOCCATA, StatoScheda.DA_ESEGUIRE):
            return None
        return self._calcola("ver", (self.new.versione, self.check_sap.versione),
                             lambda: verifica(self.check_sap.dati(), self.new.dati()))

    def sedi_per_no_wo(self) -> list[str]:
        """Sedi tecniche da modificare o rimuovere: quelle su cui cercare
        ordini e avvisi aperti."""
        ric = self.riconciliazione()
        if ric is None:
            return []
        operazioni = (Operazione.MODIFICA.value, Operazione.DA_RIMUOVERE.value)
        return sorted(ric.actual.loc[ric.actual["Operazione"].isin(operazioni), "Sede tecnica"])

    # ------------------------------------------------------------------
    # Stato delle schede
    # ------------------------------------------------------------------
    def stato(self, scheda: Scheda) -> StatoScheda:
        new_pronta = not self.new.vuota
        actual_pronta = new_pronta and self.estrazioni["actual"] is not None
        if scheda == Scheda.NEW:
            return StatoScheda.AGGIORNATA if new_pronta else StatoScheda.DA_ESEGUIRE
        if scheda == Scheda.ACTUAL:
            if not new_pronta:
                return StatoScheda.BLOCCATA
            return StatoScheda.AGGIORNATA if actual_pronta else StatoScheda.DA_ESEGUIRE
        if scheda in (Scheda.FL_DA_CREARE, Scheda.CHECK_NEW, Scheda.CHECK_ACTUAL, Scheda.CHECK_PARENT):
            return StatoScheda.AGGIORNATA if actual_pronta else StatoScheda.BLOCCATA
        if scheda == Scheda.NO_WO:
            ric = self.riconciliazione() if actual_pronta else None
            if ric is None or not ric.completa:
                return StatoScheda.BLOCCATA
            if self.estrazioni["no_wo"] is None:
                return StatoScheda.DA_ESEGUIRE
            if tuple(self.sedi_per_no_wo()) != self.sedi_no_wo:
                return StatoScheda.DA_AGGIORNARE
            return StatoScheda.AGGIORNATA
        if scheda == Scheda.CHECK:
            if not new_pronta:
                return StatoScheda.BLOCCATA
            return StatoScheda.AGGIORNATA if self.estrazioni["check"] else StatoScheda.DA_ESEGUIRE
        raise ValueError(scheda)

    # ------------------------------------------------------------------
    # Salvataggio su file
    # ------------------------------------------------------------------
    def salva(self, percorso: str | Path | None = None) -> Path:
        percorso = Path(percorso) if percorso else self.percorso
        if percorso is None:
            raise ErroreProgetto("Indicare il file in cui salvare il progetto.")
        if percorso.suffix.lower() != ESTENSIONE:
            percorso = percorso.with_name(percorso.name + ESTENSIONE)
        dati = {
            "formato": FORMATO,
            "salvato": datetime.now().isoformat(timespec="seconds"),
            "impianto": self.impianto,
            "regole": str(self.regole),
            "trasformazioni": str(self.trasformazioni),
            "avvisi_new": self.avvisi_new,
            "tabelle": {nome: getattr(self, nome).serializza()
                        for nome in ("new", "actual", "check_sap", "no_wo", "check_parent")},
            "decisioni": {s: {"tipo": d.tipo.value, "codice": d.codice} for s, d in self.decisioni.items()},
            "estrazioni": {k: v.isoformat(timespec="seconds") if v else None
                           for k, v in self.estrazioni.items()},
            "sedi_no_wo": list(self.sedi_no_wo),
        }
        temporaneo = percorso.with_name(percorso.name + ".tmp")
        try:
            with gzip.open(temporaneo, "wt", encoding="utf-8") as f:
                json.dump(dati, f, ensure_ascii=False)
            os.replace(temporaneo, percorso)        # sostituzione atomica
        except OSError as e:
            raise ErroreProgetto(f"Impossibile salvare il progetto in {percorso}: {e}") from None
        self.percorso = percorso
        ricorda_progetto(percorso)
        return percorso

    @classmethod
    def apri(cls, percorso: str | Path) -> "Progetto":
        percorso = Path(percorso)
        try:
            with gzip.open(percorso, "rt", encoding="utf-8") as f:
                dati = json.load(f)
        except (OSError, ValueError) as e:
            raise ErroreProgetto(f"Impossibile aprire il progetto {percorso.name}: {e}") from None
        if dati.get("formato") != FORMATO:
            raise ErroreProgetto(f"{percorso.name}: formato del progetto non riconosciuto.")

        p = cls(dati.get("regole", REGOLE_PREDEFINITE), dati.get("trasformazioni", TRASFORMAZIONI_PREDEFINITE))
        p.impianto = dati.get("impianto", "")
        p.avvisi_new = list(dati.get("avvisi_new", []))
        for nome, contenuto in dati.get("tabelle", {}).items():
            getattr(p, nome).ripristina_da(contenuto)
        p.decisioni = {s: Decisione(TipoDecisione(d["tipo"]), d.get("codice", ""))
                       for s, d in dati.get("decisioni", {}).items()}
        p.estrazioni = {k: datetime.fromisoformat(v) if v else None
                        for k, v in dati.get("estrazioni", {}).items()}
        for k in ("actual", "no_wo", "check"):
            p.estrazioni.setdefault(k, None)
        p.sedi_no_wo = tuple(dati.get("sedi_no_wo", []))
        p.percorso = percorso
        ricorda_progetto(percorso)
        return p
