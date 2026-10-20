"""Piano di caricamento in SAP (SPECIFICHE_SAP_SCRIPT.md, sezione 5).

Simula in sequenza le operazioni sulla struttura attuale (Actual), tenendo
conto che in SAP la modifica di una sede si propaga sempre a tutto il suo
sottoalbero, e costruisce gli step di caricamento:

- Creazione  (ZPM4R_CREA_FL): sede nuova sotto un padre esistente e definitivo;
- Modifica   (CC04): nuovo codice; il sottoalbero segue (propagazione);
- Rimozione  (CC04): spostamento nel cestino xxA-..., insieme al sottoalbero;
- Modifica descrizione (ZPM4R_CREA_FL, modalità modifica): sempre per ultima.

Gli step si susseguono nel ciclo Creazione -> Modifica -> Rimozione finché
restano operazioni; all'interno di uno step le righe sono elaborate in ordine
da SAP, quindi una riga può contare sulle precedenti. Le righe riportano il
codice che la sede avrà nel momento dello step (transcodifica).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd

from conversione_sedi.riconciliazione import Operazione, Riconciliazione, StatoNew, livello

LUNGHEZZA_DESCRIZIONE = 40          # limite del campo PLTXT in SAP
CARATTERE_CESTINO = "A"
MAX_ERRORI = 50


class TipoStep(str, Enum):
    CREAZIONE = "Creazione"
    MODIFICA = "Modifica"
    RIMOZIONE = "Rimozione"
    DESCRIZIONE = "Modifica descrizione"


@dataclass(frozen=True)
class Riga:
    sede: str            # codice nel momento dello step (Functional Location / TPLNR)
    nuovo_codice: str    # New Code (vuoto per le descrizioni)
    descrizione: str
    superiore: str       # New Superior / padre (vuoto per le descrizioni)
    originale: str = ""  # codice in Actual (vuoto per le creazioni)


@dataclass
class Step:
    numero: int
    tipo: TipoStep
    righe: list[Riga]
    propagate: list[tuple[str, str]] = field(default_factory=list)   # (codice in Actual, codice finale)


@dataclass
class Piano:
    step: list[Step] = field(default_factory=list)
    errori: list[str] = field(default_factory=list)
    avvisi: list[str] = field(default_factory=list)

    @property
    def valido(self) -> bool:
        return not self.errori


class ErroreCestino(ValueError):
    pass


# ---------------------------------------------------------------------------
# Codici
# ---------------------------------------------------------------------------
def padre(codice: str) -> str:
    return codice.rsplit("-", 1)[0] if "-" in codice else ""


def codice_cestino(codice: str) -> str:
    """Codice nel cestino: terzo carattere del primo livello sostituito da "A"
    (USE-US64-1E-02-B4 -> USA-US64-1E-02-B4)."""
    primo, _, resto = codice.partition("-")
    if len(primo) < 3:
        raise ErroreCestino(f"{codice}: il primo livello ha meno di tre caratteri.")
    if primo[2] == CARATTERE_CESTINO:
        raise ErroreCestino(f"{codice}: il terzo carattere del primo livello è già \"{CARATTERE_CESTINO}\" "
                            "(struttura del cestino).")
    nuovo = primo[:2] + CARATTERE_CESTINO + primo[3:]
    return f"{nuovo}-{resto}" if resto else nuovo


def radice_cestino(codice: str) -> str:
    return codice_cestino(codice.split("-")[0])


def firma_riconciliazione(ric: Riconciliazione) -> str:
    """Impronta dei dati da cui dipende il piano (per rilevare cambiamenti)."""
    colonne = ["Sede tecnica", "Descrizione", "Operazione", "Nuova sede tecnica", "Nuova descrizione"]
    h = hashlib.sha1()
    for riga in ric.actual[colonne].itertuples(index=False):
        h.update("\x1f".join("" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)
                             for v in riga).encode("utf-8"))
        h.update(b"\x1e")
    da_creare = ric.new[ric.new["Stato"] == StatoNew.DA_CREARE.value]
    for riga in da_creare[["Sede tecnica", "Descrizione"]].itertuples(index=False):
        h.update(("+" + "\x1f".join(map(str, riga))).encode("utf-8"))
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Simulazione
# ---------------------------------------------------------------------------
FISSA, SPOSTA, RIMUOVI, CREATA, VIRTUALE = "fissa", "sposta", "rimuovi", "creata", "virtuale"
_FISSE = {Operazione.ESCLUSA.value, Operazione.INVARIATA.value,
          Operazione.MODIFICA_DESCRIZIONE.value, Operazione.MANTENUTA.value}


def _testo(v) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


class _Nodo:
    __slots__ = ("codice", "originale", "tipo", "operazione", "destinazione", "descrizione",
                 "nuova_descrizione", "padre", "figli", "completato")

    def __init__(self, codice, tipo, originale="", operazione="", destinazione="",
                 descrizione="", nuova_descrizione=""):
        self.codice, self.tipo, self.originale = codice, tipo, originale
        self.operazione, self.destinazione = operazione, destinazione
        self.descrizione, self.nuova_descrizione = descrizione, nuova_descrizione
        self.padre: _Nodo | None = None
        self.figli: list[_Nodo] = []
        self.completato = tipo in (FISSA, VIRTUALE, CREATA)

    def discendenti(self):
        pila = list(self.figli)
        while pila:
            n = pila.pop()
            yield n
            pila.extend(n.figli)

    def antenati(self):
        n = self.padre
        while n is not None:
            yield n
            n = n.padre

    @property
    def definitivo(self) -> bool:
        """Nella posizione finale: può fare da padre a creazioni e modifiche."""
        return self.tipo in (FISSA, VIRTUALE, CREATA) or (self.tipo == SPOSTA and self.completato)


class _Simulazione:
    def __init__(self):
        self.codici: dict[str, _Nodo] = {}

    # struttura ---------------------------------------------------------
    def aggiungi(self, nodo: _Nodo) -> None:
        self.codici[nodo.codice] = nodo

    def nodo_padre(self, codice: str, crea_virtuali: bool) -> _Nodo | None:
        p = padre(codice)
        if not p:
            return None
        if p not in self.codici and crea_virtuali:
            virtuale = _Nodo(p, VIRTUALE, operazione="(esistente)")
            self.aggiungi(virtuale)
            self._collega(virtuale, self.nodo_padre(p, True))
        return self.codici.get(p)

    @staticmethod
    def _collega(nodo: _Nodo, nuovo_padre: _Nodo | None) -> None:
        if nodo.padre is not None:
            nodo.padre.figli.remove(nodo)
        nodo.padre = nuovo_padre
        if nuovo_padre is not None:
            nuovo_padre.figli.append(nodo)

    def _padre_esistente(self, codice: str) -> tuple[_Nodo | None, str | None]:
        """(nodo padre, motivo di attesa). Il livello 1 esiste sempre."""
        p = padre(codice)
        if livello(p) <= 1:
            return self.codici.get(p), None
        n = self.codici.get(p)
        if n is None:
            return None, f"manca il padre {p}"
        if not n.definitivo:
            return None, f"il padre {p} non è ancora nella posizione finale ({n.operazione})"
        return n, None

    def _sposta_sottoalbero(self, nodo: _Nodo, nuovo: str, nuovo_padre: _Nodo | None) -> list[_Nodo]:
        vecchio = nodo.codice
        sottoalbero = [nodo, *nodo.discendenti()]
        for n in sottoalbero:
            del self.codici[n.codice]
        for n in sottoalbero:
            n.codice = nuovo + n.codice[len(vecchio):]
            self.codici[n.codice] = n
        if nuovo_padre is None and livello(nuovo) > 1:        # radice di livello 1 non estratta
            nuovo_padre = self.nodo_padre(nuovo, True)
        self._collega(nodo, nuovo_padre)
        return sottoalbero[1:]

    # condizioni --------------------------------------------------------
    def attesa_creazione(self, codice: str) -> str | None:
        if codice in self.codici:
            return f"il codice {codice} è occupato da {self.codici[codice].originale or codice}"
        _, motivo = self._padre_esistente(codice)
        return motivo

    def attesa_modifica(self, nodo: _Nodo) -> str | None:
        t = nodo.destinazione
        if t in self.codici:
            return f"il codice {t} è occupato da {self.codici[t].originale or t}"
        p, motivo = self._padre_esistente(t)
        if motivo:
            return motivo
        if p is not None and (p is nodo or p in set(nodo.discendenti())):
            return f"il padre {p.codice} è nel sottoalbero della sede stessa"
        interni = {nodo, *nodo.discendenti()}
        for d in nodo.discendenti():
            nuovo = t + d.codice[len(nodo.codice):]
            if nuovo in self.codici and self.codici[nuovo] not in interni:
                return f"il codice {nuovo} (sottoalbero) è occupato"
        return None

    def attesa_rimozione(self, nodo: _Nodo) -> str | None:
        for d in nodo.discendenti():
            if d.tipo != RIMUOVI:
                return f"{d.codice} deve prima essere spostata fuori dal sottoalbero"
        nuovo = codice_cestino(nodo.codice)
        if nuovo in self.codici:
            return f"il codice {nuovo} è già usato nel cestino"
        return None

    # operazioni --------------------------------------------------------
    def crea(self, codice: str, descrizione: str) -> Riga:
        p, _ = self._padre_esistente(codice)
        nodo = _Nodo(codice, CREATA, operazione="Da creare", descrizione=descrizione)
        self.aggiungi(nodo)
        self._collega(nodo, p)
        return Riga(codice, codice, descrizione, padre(codice))

    def modifica(self, nodo: _Nodo, propagate: list) -> Riga:
        vecchio, t = nodo.codice, nodo.destinazione
        p, _ = self._padre_esistente(t)
        for d in self._sposta_sottoalbero(nodo, t, p):
            if d.tipo == SPOSTA and not d.completato and d.codice == d.destinazione:
                d.completato = True
                propagate.append((d.originale, d.codice))
        nodo.completato = True
        return Riga(vecchio, t, nodo.nuova_descrizione, padre(t), nodo.originale)

    def rimuovi(self, nodo: _Nodo, propagate: list) -> Riga:
        vecchio, nuovo = nodo.codice, codice_cestino(nodo.codice)
        radice = radice_cestino(vecchio)
        if radice not in self.codici:
            self.aggiungi(_Nodo(radice, VIRTUALE, operazione="(cestino)"))
        for d in self._sposta_sottoalbero(nodo, nuovo, self.codici[radice]):
            d.completato = True
            propagate.append((d.originale, d.codice))
        nodo.completato = True
        return Riga(vecchio, nuovo, nodo.descrizione, radice, nodo.originale)


def _ordine(codice: str):
    return livello(codice), codice


def costruisci_piano(ric: Riconciliazione) -> Piano:
    """Piano di caricamento dalla riconciliazione (deve essere completa)."""
    piano = Piano()
    if not ric.completa:
        piano.errori.append(f"Riconciliazione incompleta: {ric.righe_aperte} righe da risolvere in Check Actual.")
        return piano

    sim = _Simulazione()
    nodi: list[_Nodo] = []
    for r in sorted(ric.actual.itertuples(index=False), key=lambda r: _ordine(r[0])):
        operazione = r[ric.actual.columns.get_loc("Operazione")]
        sede = r[0]
        if operazione == Operazione.MODIFICA.value:
            tipo, dest = SPOSTA, _testo(r[ric.actual.columns.get_loc("Nuova sede tecnica")])
        elif operazione == Operazione.DA_RIMUOVERE.value:
            tipo, dest = RIMUOVI, ""
        elif operazione in _FISSE:
            tipo, dest = FISSA, sede
        else:                                               # righe aperte: già escluse sopra
            piano.errori.append(f"{sede}: operazione \"{operazione}\" non gestita.")
            continue
        nodo = _Nodo(sede, tipo, sede, operazione, dest,
                     _testo(r[ric.actual.columns.get_loc("Descrizione")]),
                     _testo(r[ric.actual.columns.get_loc("Nuova descrizione")]))
        sim.aggiungi(nodo)
        nodi.append(nodo)
    for nodo in nodi:
        sim._collega(nodo, sim.nodo_padre(nodo.codice, True))

    # errori bloccanti preliminari
    for nodo in nodi:
        if nodo.tipo == FISSA:
            trascinante = next((a for a in nodo.antenati() if a.tipo in (SPOSTA, RIMUOVI)), None)
            if trascinante is not None:
                verbo = "modifica" if trascinante.tipo == SPOSTA else "rimozione"
                piano.errori.append(f"{nodo.codice} ({nodo.operazione}) verrebbe trascinata dalla {verbo} "
                                    f"di {trascinante.codice}: assegnarle un nuovo codice o rimuoverla.")
        elif nodo.tipo == RIMUOVI:
            try:
                codice_cestino(nodo.codice)
            except ErroreCestino as e:
                piano.errori.append(str(e))
    if piano.errori:
        piano.errori = piano.errori[:MAX_ERRORI]
        return piano

    da_creare = ric.new[ric.new["Stato"] == StatoNew.DA_CREARE.value]
    creazioni = {s: _testo(d) for s, d in zip(da_creare["Sede tecnica"], da_creare["Descrizione"])}
    spostamenti = [n for n in nodi if n.tipo == SPOSTA]
    rimozioni = [n for n in nodi if n.tipo == RIMUOVI]

    def in_sospeso():
        return bool(creazioni) or any(not n.completato for n in spostamenti + rimozioni)

    while in_sospeso():
        eseguito = False
        for tipo in (TipoStep.CREAZIONE, TipoStep.MODIFICA, TipoStep.RIMOZIONE):
            righe: list[Riga] = []
            propagate: list[tuple[str, str]] = []
            cambiato = True
            while cambiato:                                 # le righe possono contare sulle precedenti
                cambiato = False
                if tipo == TipoStep.CREAZIONE:
                    for codice in sorted(creazioni, key=_ordine):
                        if sim.attesa_creazione(codice) is None:
                            righe.append(sim.crea(codice, creazioni.pop(codice)))
                            cambiato = True
                elif tipo == TipoStep.MODIFICA:
                    for n in sorted((n for n in spostamenti if not n.completato), key=lambda n: _ordine(n.codice)):
                        if not n.completato and sim.attesa_modifica(n) is None:
                            righe.append(sim.modifica(n, propagate))
                            cambiato = True
                else:
                    for n in sorted((n for n in rimozioni if not n.completato), key=lambda n: _ordine(n.codice)):
                        if n.completato or any(a.tipo == RIMUOVI and not a.completato for a in n.antenati()):
                            continue                        # la rimuove la sede più alta
                        if sim.attesa_rimozione(n) is None:
                            righe.append(sim.rimuovi(n, propagate))
                            cambiato = True
            if righe:
                piano.step.append(Step(len(piano.step) + 1, tipo, righe, propagate))
                eseguito = True
        if not eseguito:
            for codice in sorted(creazioni, key=_ordine):
                piano.errori.append(f"Creazione di {codice} bloccata: {sim.attesa_creazione(codice)}.")
            for n in spostamenti:
                if not n.completato:
                    piano.errori.append(f"Modifica di {n.originale} in {n.destinazione} bloccata "
                                        f"(codice attuale {n.codice}): {sim.attesa_modifica(n)}.")
            for n in rimozioni:
                if not n.completato and not any(a.tipo == RIMUOVI for a in n.antenati()):
                    piano.errori.append(f"Rimozione di {n.originale} bloccata: {sim.attesa_rimozione(n)}.")
            piano.errori = piano.errori[:MAX_ERRORI] or ["Piano non risolvibile: dipendenza circolare."]
            piano.step = []
            return piano

    descrizioni = [Riga(n.codice, "", n.nuova_descrizione, "", n.originale)
                   for n in sorted(nodi, key=lambda n: _ordine(n.codice))
                   if n.operazione == Operazione.MODIFICA_DESCRIZIONE.value]
    if descrizioni:
        piano.step.append(Step(len(piano.step) + 1, TipoStep.DESCRIZIONE, descrizioni))

    lunghe = sorted({r.nuovo_codice or r.sede for s in piano.step for r in s.righe
                     if len(r.descrizione) > LUNGHEZZA_DESCRIZIONE})
    if lunghe:
        piano.avvisi.append(f"Descrizioni più lunghe di {LUNGHEZZA_DESCRIZIONE} caratteri ({len(lunghe)}): "
                            + ", ".join(lunghe[:20]) + (" ..." if len(lunghe) > 20 else "") + ".")
    return piano
