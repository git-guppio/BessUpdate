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
from conversione_sedi.file_sap import FILE_DISPONIBILE, nome_file, scrivi_piano
from conversione_sedi.ingresso_uscita import REGOLE_PREDEFINITE, TRASFORMAZIONI_PREDEFINITE
from conversione_sedi.nucleo import carica_configurazione, elabora_dataframe
from conversione_sedi.nuova_codifica import NuovaCodifica, appartiene
from conversione_sedi.piano_sap import Piano, Riga, Step, TipoStep, costruisci_piano, firma_riconciliazione
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
    SAP_SCRIPT = "SAP script"
    CHECK = "Check"


class StatoScheda(str, Enum):
    BLOCCATA = "Bloccata"               # passaggi precedenti non eseguiti
    DA_ESEGUIRE = "Da eseguire"         # disponibile, mai eseguita
    AGGIORNATA = "Aggiornata"
    DA_AGGIORNARE = "Da aggiornare"     # estrazione SAP basata su dati cambiati


class StatoStep(str, Enum):
    DA_CARICARE = "Da caricare"
    CARICATO = "Caricato - da validare"
    VALIDATO = "Validato"
    CON_ERRORI = "Con errori"


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
        # piano di caricamento in SAP (step SAP script)
        self.piano: Piano | None = None
        self.piano_firma = ""
        self.piano_cartella: Path | None = None
        self.piano_generato: datetime | None = None
        self.stati_step: list[StatoStep] = []
        for tabella in (self.new, self.actual, self.no_wo, self.check_parent):
            tabella.blocco = self._messaggio_blocco
        self._cache.clear()

    # ------------------------------------------------------------------
    # Blocco dei dati durante l'esecuzione del piano (D10)
    # ------------------------------------------------------------------
    @property
    def piano_in_esecuzione(self) -> bool:
        return any(s != StatoStep.DA_CARICARE for s in self.stati_step)

    def _messaggio_blocco(self) -> str | None:
        if self.piano_in_esecuzione:
            return ("Piano di caricamento in esecuzione: i dati non si possono modificare. "
                    "Per cambiarli usare \"Interrompi piano\" nello step SAP script.")
        return None

    def _controlla_sblocco(self) -> None:
        messaggio = self._messaggio_blocco()
        if messaggio:
            raise ErroreProgetto(messaggio)

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
        self._controlla_sblocco()
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
        self._controlla_sblocco()
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
        self._controlla_sblocco()
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
        self._controlla_sblocco()
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
        """Sedi tecniche da rimuovere: quelle su cui ordini e avvisi devono
        essere chiusi (D2). Le sedi solo modificate mantengono l'ID interno SAP."""
        ric = self.riconciliazione()
        if ric is None:
            return []
        return sorted(ric.actual.loc[ric.actual["Operazione"] == Operazione.DA_RIMUOVERE.value, "Sede tecnica"])

    def no_wo_aperti(self) -> int:
        """Ordini e avvisi trovati dall'ultima estrazione No_Wo (le righe tolte
        a mano non contano: serve una nuova estrazione, D4)."""
        return self.no_wo.righe_importate

    # ------------------------------------------------------------------
    # Piano di caricamento (step SAP script)
    # ------------------------------------------------------------------
    def cartella_file_sap(self) -> Path | None:
        if self.percorso is None:
            return None
        return self.percorso.parent / f"SAP_{self.impianto}"

    def genera_piano(self) -> Piano:
        """Costruisce il piano e scrive i file. Se il piano ha errori non
        scrive nulla e lo restituisce con gli errori."""
        self._controlla_sblocco()
        motivo = self.motivo_blocco(Scheda.SAP_SCRIPT)
        if motivo:
            raise ErroreProgetto(f"Impossibile generare i file: {motivo}")
        ric = self.riconciliazione()
        piano = costruisci_piano(ric)
        if not piano.valido:
            return piano
        cartella = self.cartella_file_sap()
        scrivi_piano(piano, cartella)
        self.piano, self.piano_firma, self.piano_cartella = piano, firma_riconciliazione(ric), cartella
        self.piano_generato = datetime.now()
        self.stati_step = [StatoStep.DA_CARICARE] * len(piano.step)
        self._modificato()
        return piano

    def file_step(self, numero: int) -> Path | None:
        """File del step (None per gli step senza file, es. creazione)."""
        step = self.piano.step[numero - 1]
        if not FILE_DISPONIBILE[step.tipo] or self.piano_cartella is None:
            return None
        return self.piano_cartella / nome_file(step)

    def step_corrente(self) -> int | None:
        """Numero del primo step non ancora validato (None se il piano è completato)."""
        for i, stato in enumerate(self.stati_step):
            if stato != StatoStep.VALIDATO:
                return i + 1
        return None

    def _controlla_step(self, numero: int, ammessi: tuple[StatoStep, ...]) -> None:
        if self.piano is None:
            raise ErroreProgetto("Nessun piano di caricamento: generare prima i file.")
        if self.stato(Scheda.SAP_SCRIPT) == StatoScheda.DA_AGGIORNARE:
            raise ErroreProgetto("I dati sono cambiati dopo la generazione dei file: rigenerarli.")
        if numero != self.step_corrente():
            raise ErroreProgetto(f"Si può operare solo sullo step {self.step_corrente()}: "
                                 "gli step vanno caricati e validati in ordine.")
        if self.stati_step[numero - 1] not in ammessi:
            raise ErroreProgetto(f"Step {numero}: operazione non ammessa nello stato "
                                 f"\"{self.stati_step[numero - 1].value}\".")

    def segna_caricato(self, numero: int) -> None:
        """Il file dello step è stato caricato in SAP: l'esito va validato."""
        self._controlla_step(numero, (StatoStep.DA_CARICARE, StatoStep.CON_ERRORI))
        self.stati_step[numero - 1] = StatoStep.CARICATO
        self._modificato()

    def registra_esito(self, numero: int, ok: bool) -> None:
        """Esito del caricamento verificato dall'utente sui messaggi SAP (D8)."""
        self._controlla_step(numero, (StatoStep.CARICATO,))
        self.stati_step[numero - 1] = StatoStep.VALIDATO if ok else StatoStep.CON_ERRORI
        self._modificato()

    def interrompi_piano(self) -> None:
        """Abbandona il piano: i dati tornano modificabili (D10). I file
        restano nella cartella fino alla prossima generazione."""
        self.piano, self.piano_firma, self.piano_generato = None, "", None
        self.stati_step = []
        self._modificato()

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
            if not self.sedi_per_no_wo():
                return StatoScheda.AGGIORNATA           # nessuna sede da rimuovere: nulla da verificare
            if self.estrazioni["no_wo"] is None:
                return StatoScheda.DA_ESEGUIRE
            if tuple(self.sedi_per_no_wo()) != self.sedi_no_wo:
                return StatoScheda.DA_AGGIORNARE
            return StatoScheda.AGGIORNATA
        if scheda == Scheda.SAP_SCRIPT:
            if self.motivo_blocco(scheda):
                return StatoScheda.BLOCCATA
            if self.piano is None:
                return StatoScheda.DA_ESEGUIRE
            ric = self.riconciliazione()
            if ric is None or firma_riconciliazione(ric) != self.piano_firma:
                return StatoScheda.DA_AGGIORNARE
            return StatoScheda.AGGIORNATA
        if scheda == Scheda.CHECK:
            if not new_pronta:
                return StatoScheda.BLOCCATA
            return StatoScheda.AGGIORNATA if self.estrazioni["check"] else StatoScheda.DA_ESEGUIRE
        raise ValueError(scheda)

    def motivo_blocco(self, scheda: Scheda) -> str | None:
        """Motivo per cui la scheda è bloccata (None se non lo è)."""
        if scheda != Scheda.SAP_SCRIPT:
            return None
        if self.piano_in_esecuzione:
            return None                                 # il piano avviato resta utilizzabile
        if self.stato(Scheda.CHECK_ACTUAL) == StatoScheda.BLOCCATA:
            return "estrarre prima i dati da SAP (Actual)."
        if not self.riconciliazione().completa:
            return "completare la riconciliazione (righe da risolvere in Check Actual)."
        stato_no_wo = self.stato(Scheda.NO_WO)
        if stato_no_wo == StatoScheda.DA_ESEGUIRE:
            return "verificare ordini e avvisi sulle sedi da rimuovere (No_Wo, pulsante Aggiorna)."
        if stato_no_wo == StatoScheda.DA_AGGIORNARE:
            return "le sedi da rimuovere sono cambiate: aggiornare l'estrazione No_Wo."
        if self.sedi_per_no_wo() and self.no_wo_aperti():
            return (f"{self.no_wo_aperti()} Work Order / Notification aperti su sedi da rimuovere: "
                    "chiuderli in SAP e aggiornare l'estrazione No_Wo.")
        if self.percorso is None:
            return "salvare il progetto: i file vengono creati accanto al file di progetto."
        return None

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
            "piano": _serializza_piano(self),
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
        _ripristina_piano(p, dati.get("piano"))
        p.percorso = percorso
        ricorda_progetto(percorso)
        return p


# ---------------------------------------------------------------------------
# Salvataggio del piano
# ---------------------------------------------------------------------------
def _serializza_piano(p: Progetto) -> dict | None:
    if p.piano is None:
        return None
    return {
        "firma": p.piano_firma,
        "cartella": str(p.piano_cartella) if p.piano_cartella else None,
        "generato": p.piano_generato.isoformat(timespec="seconds") if p.piano_generato else None,
        "stati": [s.value for s in p.stati_step],
        "avvisi": p.piano.avvisi,
        "step": [{"numero": s.numero, "tipo": s.tipo.value,
                  "righe": [[r.sede, r.nuovo_codice, r.descrizione, r.superiore, r.originale] for r in s.righe],
                  "propagate": [list(x) for x in s.propagate]} for s in p.piano.step],
    }


def _ripristina_piano(p: Progetto, dati: dict | None) -> None:
    if not dati:
        return
    p.piano = Piano(step=[Step(s["numero"], TipoStep(s["tipo"]), [Riga(*r) for r in s["righe"]],
                               [tuple(x) for x in s.get("propagate", [])]) for s in dati["step"]],
                    avvisi=list(dati.get("avvisi", [])))
    p.piano_firma = dati.get("firma", "")
    p.piano_cartella = Path(dati["cartella"]) if dati.get("cartella") else None
    p.piano_generato = datetime.fromisoformat(dati["generato"]) if dati.get("generato") else None
    p.stati_step = [StatoStep(v) for v in dati.get("stati", [])]
