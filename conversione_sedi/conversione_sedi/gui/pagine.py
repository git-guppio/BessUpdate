"""Le schede della finestra principale (SPECIFICHE_GUI.md, sezione 4)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from conversione_sedi.check_parent import CHECK_DUPLICATO, CHECK_OK, CHECK_PARENT, CHECK_VUOTA, riepilogo
from conversione_sedi.gui.attesa import esegui_con_attesa
from conversione_sedi.gui.pannello import DelegatoCompletamento, PannelloTabella
from conversione_sedi.nucleo import ESITO_DA_VERIFICARE, ESITO_NESSUNA_CORRISPONDENZA, ESITO_OK, ESITO_VUOTA
from conversione_sedi.nuova_codifica import carica_new
from conversione_sedi.progetto import ImpiantoDiverso, Scheda, StatoScheda
from conversione_sedi.riconciliazione import Decisione, Operazione, StatoNew
from conversione_sedi.tabella import COL_NOTE, Tabella
from conversione_sedi.verifica import ESITI, categoria as categoria_verifica

MOTIVI_BLOCCO = {
    Scheda.ACTUAL: "caricare prima la nuova codifica (New).",
    Scheda.FL_DA_CREARE: "estrarre prima i dati da SAP (Actual).",
    Scheda.CHECK_NEW: "estrarre prima i dati da SAP (Actual).",
    Scheda.CHECK_ACTUAL: "estrarre prima i dati da SAP (Actual).",
    Scheda.CHECK_PARENT: "estrarre prima i dati da SAP (Actual).",
    Scheda.NO_WO: "completare la riconciliazione (nessuna riga Da decidere, Da verificare o Conflitto "
                  "nella scheda Check Actual).",
    Scheda.CHECK: "caricare prima la nuova codifica (New).",
}


def _data(d) -> str:
    return d.strftime("%d/%m/%Y %H:%M") if d else ""


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------
class Pagina(QWidget):
    scheda: Scheda
    descrizione = ""

    def __init__(self, finestra):
        super().__init__()
        self.f = finestra
        self.pannello = PannelloTabella(self.scheda.value.replace(" ", "_"))
        self.pannello.cartella_esportazione = finestra.cartella_lavoro
        self.pannello.modello.modificaRichiesta.connect(
            lambda r, c, v: self.esegui(lambda: self.modifica(r, c, v)))
        self.pannello.azioni_contestuali = self.azioni
        self.pannello.pulsante_esporta.clicked.disconnect()
        self.pannello.pulsante_esporta.clicked.connect(lambda: self.esegui(self.pannello.esporta))
        self._pulsanti_operativi: list[QPushButton] = []

        titolo = QLabel(self.scheda.value)
        titolo.setStyleSheet("font-size: 15pt; font-weight: 600;")
        descrizione = QLabel(self.descrizione)
        descrizione.setWordWrap(True)
        descrizione.setStyleSheet("color: #555;")
        self.avviso = QLabel()
        self.avviso.setWordWrap(True)
        self.avviso.setVisible(False)
        self.avviso.setStyleSheet("background: #FFF3CD; color: #3D3000; border: 1px solid #E0C46C; padding: 6px;")

        self.layout_principale = QVBoxLayout(self)
        self.layout_principale.addWidget(titolo)
        self.layout_principale.addWidget(descrizione)
        self.layout_principale.addWidget(self.avviso)
        self.layout_principale.addWidget(self.pannello, 1)

    @property
    def p(self):
        return self.f.progetto

    def pulsante(self, testo: str, azione) -> QPushButton:
        b = self.pannello.aggiungi_pulsante(testo, lambda: self.esegui(azione))
        self._pulsanti_operativi.append(b)
        return b

    def esegui(self, azione) -> None:
        """Esecuzione di un'azione dell'utente con gestione degli errori e aggiornamento."""
        try:
            azione()
        except Exception as e:                   # messaggio leggibile, mai traceback
            self.f.errore(e)
        self.f.aggiorna()

    def mostra_avviso(self, testo: str | None) -> None:
        self.avviso.setText(testo or "")
        self.avviso.setVisible(bool(testo))

    # da ridefinire
    def aggiorna(self) -> None:
        stato = self.p.stato(self.scheda)
        bloccata = stato == StatoScheda.BLOCCATA
        for b in self._pulsanti_operativi:
            b.setEnabled(not bloccata)
        if bloccata:
            self.pannello.imposta_dati(pd.DataFrame())
            self.pannello.info.setText("")
            self.mostra_avviso(f"Scheda bloccata: {MOTIVI_BLOCCO.get(self.scheda, '')}")
            return
        self.mostra_avviso(None)
        self.mostra()

    def mostra(self) -> None:
        pass

    def modifica(self, riga: int, colonna: str, valore: str) -> None:
        pass

    def azioni(self, righe: list[int], colonna: str | None) -> list:
        return []


class PaginaTabella(Pagina):
    """Scheda basata su una Tabella con modifiche manuali (sezione 3.3)."""

    def tabella(self) -> Tabella:
        raise NotImplementedError

    def mostra_tabella(self, vista: pd.DataFrame, meta, colonna_esito=None) -> None:
        t = self.tabella()
        self.pannello.imposta_dati(vista, meta=meta, colonna_esito=colonna_esito,
                                   modificabili=set(t.colonne) | {COL_NOTE})

    def modifica(self, riga, colonna, valore):
        meta = self.pannello.modello.meta_riga(riga)
        if colonna == COL_NOTE:
            self.tabella().imposta_nota(meta.chiave, valore)
        else:
            self.tabella().modifica(meta.chiave, colonna, valore)

    def azioni(self, righe, colonna):
        modello = self.pannello.modello
        meta = [modello.meta_riga(r) for r in righe]
        t = self.tabella()

        def azione(testo, funzione, abilitata=True):
            a = QAction(testo)
            a.triggered.connect(lambda: self.esegui(funzione))
            a.setEnabled(abilitata)
            return a

        cella_modificata = len(righe) == 1 and colonna is not None and colonna in meta[0].originali
        return [
            azione("Inserisci riga…", self.inserisci),
            azione("Rimuovi righe selezionate", lambda: [t.rimuovi(m.chiave) for m in meta if not m.rimossa],
                   any(not m.rimossa for m in meta)),
            azione("Ripristina righe rimosse", lambda: [t.ripristina(m.chiave) for m in meta if m.rimossa],
                   any(m.rimossa for m in meta)),
            azione("Ripristina valore originale",
                   lambda: t.ripristina_cella(meta[0].chiave, colonna), cella_modificata),
            None,
        ]

    def inserisci(self) -> None:
        t = self.tabella()
        dialogo = QDialog(self)
        dialogo.setWindowTitle("Inserisci riga")
        modulo = QFormLayout(dialogo)
        campi = {c: QLineEdit() for c in t.colonne}
        for c, campo in campi.items():
            modulo.addRow(c, campo)
        pulsanti = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        pulsanti.accepted.connect(dialogo.accept)
        pulsanti.rejected.connect(dialogo.reject)
        modulo.addRow(pulsanti)
        dialogo.setMinimumWidth(420)
        if dialogo.exec():
            t.aggiungi({c: campo.text() for c, campo in campi.items()})


# ---------------------------------------------------------------------------
# New
# ---------------------------------------------------------------------------
class PaginaNew(PaginaTabella):
    scheda = Scheda.NEW
    descrizione = "Nuova codifica proposta, caricata da file Excel (colonne \"Sede tecnica\" e \"Descrizione\")."

    def __init__(self, finestra):
        super().__init__(finestra)
        self.pannello.aggiungi_pulsante("Carica Excel…", lambda: self.esegui(self.carica))

    def tabella(self):
        return self.p.new

    def aggiorna(self):
        self.mostra_avviso("; ".join(self.p.avvisi_new) or None)
        self.mostra()

    def mostra(self):
        vista, meta = self.p.new.vista()
        self.mostra_tabella(vista, meta)
        self.pannello.info.setText(f"Impianto: {self.p.impianto}" if self.p.impianto else
                                   "Nessuna nuova codifica caricata.")

    def carica(self):
        percorso, _ = QFileDialog.getOpenFileName(self, "Carica nuova codifica", self.f.cartella_lavoro(),
                                                  "File Excel o CSV (*.xlsx *.xlsm *.csv)")
        if not percorso:
            return
        nc = carica_new(percorso)
        try:
            conserva = True
            if self.p.new.conta_modifiche():
                conserva = self.f.chiedi_conserva(self.p.new.conta_modifiche(), "New")
                if conserva is None:
                    return
            self.p.imposta_new(nc, conserva_modifiche=conserva)
        except ImpiantoDiverso as e:
            if not self.f.conferma(f"{e}\n\nCaricando questo file tutto il lavoro sull'impianto "
                                   f"{e.attuale} verrà scartato. Continuare?"):
                return
            self.p.imposta_new(nc, azzera=True)
        self.f.assicura_percorso(Path(percorso).parent, nc.impianto)


# ---------------------------------------------------------------------------
# Actual
# ---------------------------------------------------------------------------
class PaginaActual(PaginaTabella):
    scheda = Scheda.ACTUAL
    descrizione = ("Sedi tecniche presenti in SAP (IH06, layout FL_BESS_MIG), escluse quelle con stato "
                   "CANC, OGIN o FCAN. Base di partenza della riconciliazione.")

    def __init__(self, finestra):
        super().__init__(finestra)
        self.pulsante("Estrai da SAP (IH06)", self.estrai)

    def tabella(self):
        return self.p.actual

    def mostra(self):
        vista, meta = self.p.actual.vista()
        self.mostra_tabella(vista, meta)
        quando = self.p.estrazioni["actual"]
        self.pannello.info.setText(f"Estrazione del {_data(quando)}" if quando else "Estrazione non ancora eseguita.")

    def estrai(self):
        from conversione_sedi.sap import connetti_sessione, estrai_sedi_ih06
        conserva = True
        n = self.p.conta_modifiche_manuali(Scheda.ACTUAL)
        if self.p.estrazioni["actual"] and not self.f.conferma(
                "Actual è già stato estratto: è la base di tutta la pianificazione.\n"
                "Eseguire una nuova estrazione da SAP?"):
            return
        if n:
            conserva = self.f.chiedi_conserva(n, "Actual e nelle decisioni di Check Actual")
            if conserva is None:
                return
        impianto = self.p.impianto
        df = esegui_con_attesa(self.f, f"Estrazione IH06 di {impianto}* in corso…",
                               lambda: estrai_sedi_ih06(connetti_sessione(), impianto))
        self.p.imposta_actual(df, conserva_modifiche=conserva)
        self.f.statusBar().showMessage(f"IH06: estratte {len(df)} Sedi tecniche.", 8000)


# ---------------------------------------------------------------------------
# FL da creare
# ---------------------------------------------------------------------------
class PaginaFL(Pagina):
    scheda = Scheda.FL_DA_CREARE
    descrizione = "Conversione delle Sedi di Actual con le regole (config/regole.csv e trasformazioni.csv)."

    def __init__(self, finestra):
        super().__init__(finestra)
        self.pannello.imposta_esiti([ESITO_OK, ESITO_DA_VERIFICARE, ESITO_NESSUNA_CORRISPONDENZA, ESITO_VUOTA])

    def mostra(self):
        df = self.p.fl_da_creare()
        self.pannello.imposta_dati(df, colonna_esito="Esito")
        conteggi = df["Esito"].value_counts()
        self.pannello.info.setText(" · ".join(f"{e}: {int(n)}" for e, n in conteggi.items()))


# ---------------------------------------------------------------------------
# Check New / Check Actual
# ---------------------------------------------------------------------------
class PaginaCheckNew(Pagina):
    scheda = Scheda.CHECK_NEW
    descrizione = "Per ogni Sede di New: esiste già in SAP, deriva dalla modifica di una Sede di Actual o va creata."

    def __init__(self, finestra):
        super().__init__(finestra)
        self.pannello.imposta_esiti([s.value for s in StatoNew])

    def mostra(self):
        ric = self.p.riconciliazione()
        self.pannello.imposta_dati(ric.new, colonna_esito="Stato")
        self.pannello.info.setText(" · ".join(f"{s}: {n}" for s, n in ric.riepilogo_new().items() if n))


class PaginaCheckActual(Pagina):
    scheda = Scheda.CHECK_ACTUAL
    descrizione = ("Per ogni Sede di SAP: l'operazione da eseguire. Doppio clic su \"Nuova sede tecnica\" "
                   "per assegnare un codice a mano; clic destro per le altre decisioni.")
    COLONNA_CODICE = "Nuova sede tecnica"

    def __init__(self, finestra):
        super().__init__(finestra)
        self.pannello.imposta_esiti([o.value for o in Operazione])
        self._delegato = DelegatoCompletamento(
            lambda: self.p.new.dati()["Sede tecnica"].tolist(), self.pannello.vista)

    ORDINE_COLONNE = ("Sede tecnica", "Descrizione", "Operazione", "Nuova sede tecnica", "Nuova descrizione",
                      "Motivo", "Decisione manuale", "Sequenza", "Codice_Out", "Esito conversione")

    def mostra(self):
        ric = self.p.riconciliazione()
        df = ric.actual[list(self.ORDINE_COLONNE)]
        manuali = [i for i, v in enumerate(df["Decisione manuale"]) if v]
        motivi = df["Motivo"].tolist()
        self.pannello.imposta_dati(
            df, colonna_esito="Operazione", modificabili={self.COLONNA_CODICE}, righe_manuali=manuali,
            tooltip=lambda r, c: motivi[r] if c == "Operazione" else None)
        indice = list(df.columns).index(self.COLONNA_CODICE)
        self.pannello.vista.setItemDelegateForColumn(indice, self._delegato)
        if ric.completa:
            self.pannello.info.setText("Riconciliazione completa: ogni Sede ha un'operazione definita.")
            self.pannello.info.setStyleSheet("color: #1E7B34;")
        else:
            self.pannello.info.setText(f"Righe da risolvere: {ric.righe_aperte} "
                                       "(Da decidere, Da verificare, Conflitto) — generazione del file bloccata.")
            self.pannello.info.setStyleSheet("color: #B02A37;")

    def _sede(self, riga: int) -> str:
        return self.pannello.modello.valore(riga, "Sede tecnica")

    def modifica(self, riga, colonna, valore):
        sede = self._sede(riga)
        valore = valore.strip()
        self.p.imposta_decisione(sede, Decisione.nuovo_codice(valore) if valore else None)

    def azioni(self, righe, colonna):
        sedi = [self._sede(r) for r in righe]
        ric = self.p.riconciliazione()

        def azione(testo, funzione, abilitata=True):
            a = QAction(testo)
            a.triggered.connect(lambda: self.esegui(funzione))
            a.setEnabled(abilitata and bool(sedi))
            return a

        def decidi(decisione):
            return lambda: [self.p.imposta_decisione(s, decisione) for s in sedi]

        gruppo = ric.gruppi_conflitto.get(sedi[0], []) if len(sedi) == 1 else []
        return [
            azione("Da rimuovere", decidi(Decisione.rimuovi())),
            azione("Mantieni invariata", decidi(Decisione.mantieni())),
            azione("Torna all'automatico", decidi(None), any(s in self.p.decisioni for s in sedi)),
            None,
            azione("Scegli questa (conflitto): le altre diventano Da rimuovere",
                   lambda: self.p.risolvi_conflitto(sedi[0], gruppo), bool(gruppo)),
            None,
        ]


# ---------------------------------------------------------------------------
# Check Parent
# ---------------------------------------------------------------------------
def _categoria_check(valore: str) -> str:
    if valore.startswith(CHECK_DUPLICATO):
        return CHECK_DUPLICATO
    if valore.startswith(CHECK_PARENT):
        return CHECK_PARENT
    return valore


class PaginaCheckParent(PaginaTabella):
    scheda = Scheda.CHECK_PARENT
    descrizione = ("Stato finale dopo il caricamento in SAP: verifica dei duplicati e della presenza "
                   "del parent diretto di ogni Sede.")

    def __init__(self, finestra):
        super().__init__(finestra)
        self.pulsante("Check", self.check)
        self.pannello.imposta_esiti([CHECK_OK, CHECK_DUPLICATO, CHECK_PARENT, CHECK_VUOTA], _categoria_check)

    def tabella(self):
        return self.p.check_parent

    def mostra(self):
        vista, meta = self.p.check_parent_vista()
        self.mostra_tabella(vista, meta, colonna_esito="Check")
        validi = vista[[not m.rimossa for m in meta]] if meta else vista
        conteggi = riepilogo(validi) if len(validi) else {}
        self.pannello.info.setText(" · ".join(f"{k}: {v}" for k, v in conteggi.items() if v))

    def check(self):
        vista, meta = self.p.check_parent_vista()
        validi = vista[[not m.rimossa for m in meta]]
        conteggi = riepilogo(validi)
        errori = conteggi[CHECK_DUPLICATO] + conteggi[CHECK_PARENT] + conteggi[CHECK_VUOTA]
        self.f.informa("Check Parent", "Nessun errore: la gerarchia è completa." if not errori else
                       f"Righe con errori: {errori}\n" + "\n".join(f"{k}: {v}" for k, v in conteggi.items()))


# ---------------------------------------------------------------------------
# No_Wo
# ---------------------------------------------------------------------------
class PaginaNoWo(PaginaTabella):
    scheda = Scheda.NO_WO
    descrizione = ("Work Order (IW39) e Notification (IW29) non chiusi sulle Sedi tecniche da modificare "
                   "o rimuovere: possono bloccare le operazioni in SAP.")

    def __init__(self, finestra):
        super().__init__(finestra)
        self.pulsante("Aggiorna (IW39 / IW29)", self.estrai)

    def tabella(self):
        return self.p.no_wo

    def aggiorna(self):
        super().aggiorna()
        if self.p.stato(self.scheda) == StatoScheda.BLOCCATA:
            if not self.p.no_wo.vuota:                 # dati di un'estrazione precedente
                self.mostra()
        elif self.p.stato(self.scheda) == StatoScheda.DA_AGGIORNARE:
            self.mostra_avviso("Le Sedi da modificare o rimuovere sono cambiate dopo l'ultima estrazione: "
                               "premere Aggiorna.")

    def mostra(self):
        vista, meta = self.p.no_wo.vista()
        self.mostra_tabella(vista, meta)
        quando = self.p.estrazioni["no_wo"]
        n = len(self.p.sedi_per_no_wo())
        self.pannello.info.setText(f"Sedi da verificare: {n}"
                                   + (f" · estrazione del {_data(quando)}" if quando else ""))

    def estrai(self):
        from conversione_sedi.sap import connetti_sessione, estrai_avvisi_iw29, estrai_ordini_iw39
        sedi = self.p.sedi_per_no_wo()
        conserva = True
        n = self.p.conta_modifiche_manuali(Scheda.NO_WO)
        if n:
            conserva = self.f.chiedi_conserva(n, "No_Wo")
            if conserva is None:
                return

        def estrai():
            if not sedi:
                vuoto = pd.DataFrame(columns=["Sede tecnica", "Work Order", "Notification", "Descrizione", "Stato"])
                return vuoto, vuoto
            sessione = connetti_sessione()
            return estrai_ordini_iw39(sessione, sedi), estrai_avvisi_iw29(sessione, sedi)

        ordini, avvisi = esegui_con_attesa(self.f, f"Estrazione IW39 / IW29 su {len(sedi)} Sedi in corso…", estrai)
        self.p.imposta_no_wo(ordini, avvisi, sedi, conserva_modifiche=conserva)
        self.f.statusBar().showMessage(f"Estratti {len(ordini)} Work Order e {len(avvisi)} Notification.", 8000)


# ---------------------------------------------------------------------------
# Check (verifica dopo il caricamento)
# ---------------------------------------------------------------------------
class PannelloStatistiche(QFrame):
    def __init__(self, pagina: "PaginaCheck"):
        super().__init__()
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumWidth(240)
        self.pagina = pagina
        layout = QVBoxLayout(self)
        titolo = QLabel("Statistiche")
        titolo.setStyleSheet("font-weight: 600; font-size: 12pt;")
        layout.addWidget(titolo)
        self.data = QLabel()
        self.data.setStyleSheet("color: #555;")
        layout.addWidget(self.data)
        self.totale = QLabel()
        layout.addWidget(self.totale)
        self.voci: dict[str, QPushButton] = {}
        for esito in ESITI:
            b = QPushButton()
            b.setFlat(True)
            b.setStyleSheet("text-align: left; padding: 4px;")
            b.setToolTip("Mostra solo queste righe")
            b.clicked.connect(lambda _=False, e=esito: pagina.pannello.seleziona_esito(e))
            self.voci[esito] = b
            layout.addWidget(b)
        tutti = QPushButton("Mostra tutte")
        tutti.setFlat(True)
        tutti.setStyleSheet("text-align: left; padding: 4px; color: #0B5ED7;")
        tutti.clicked.connect(lambda: pagina.pannello.seleziona_esito("Tutti gli esiti"))
        layout.addWidget(tutti)
        layout.addSpacing(12)
        layout.addWidget(QLabel("Allineamento"))
        self.barra = QProgressBar()
        self.barra.setRange(0, 1000)
        layout.addWidget(self.barra)
        layout.addStretch(1)

    def aggiorna(self, v, quando) -> None:
        self.data.setText(f"Estrazione del {_data(quando)}")
        self.totale.setText(f"Totale confrontato: {v.totale}")
        conteggi, perc = v.conteggi(), v.percentuali()
        for esito, b in self.voci.items():
            testo = f"{esito}: {conteggi[esito]}"
            if esito != "Esclusa (livello 1-2)":
                testo += f"  ({perc[esito]:.1f}%)"
            b.setText(testo)
        self.barra.setValue(int(v.allineamento * 10))
        self.barra.setFormat(f"{v.allineamento:.1f}%")


class PaginaCheck(Pagina):
    scheda = Scheda.CHECK
    descrizione = ("Verifica dopo il caricamento: confronto diretto tra le Sedi presenti in SAP (IH06) "
                   "e la nuova codifica (New). Le Sedi mancanti in SAP sono in fondo alla tabella.")

    def __init__(self, finestra):
        super().__init__(finestra)
        self.pulsante("Aggiorna da SAP (IH06)", self.estrai)
        self.pannello.imposta_esiti(list(ESITI), categoria_verifica)
        self.statistiche = PannelloStatistiche(self)
        self.layout_principale.removeWidget(self.pannello)
        contenitore = QHBoxLayout()
        contenitore.addWidget(self.pannello, 1)
        contenitore.addWidget(self.statistiche)
        self.layout_principale.addLayout(contenitore, 1)

    def aggiorna(self):
        super().aggiorna()
        self.statistiche.setVisible(self.p.verifica() is not None)

    def mostra(self):
        v = self.p.verifica()
        if v is None:
            self.pannello.imposta_dati(pd.DataFrame())
            self.pannello.info.setText("Estrazione non ancora eseguita.")
            return
        self.pannello.imposta_dati(v.dati, colonna_esito="Esito check")
        self.pannello.info.setText("SAP è allineato con New." if v.allineato
                                   else f"Allineamento: {v.allineamento:.1f}%")
        self.statistiche.aggiorna(v, self.p.estrazioni["check"])

    def estrai(self):
        from conversione_sedi.sap import connetti_sessione, estrai_sedi_ih06
        impianto = self.p.impianto
        df = esegui_con_attesa(self.f, f"Estrazione IH06 di {impianto}* in corso…",
                               lambda: estrai_sedi_ih06(connetti_sessione(), impianto))
        self.p.imposta_check_sap(df)
        self.f.statusBar().showMessage(f"IH06: estratte {len(df)} Sedi tecniche.", 8000)


PAGINE = (PaginaNew, PaginaActual, PaginaFL, PaginaCheckNew, PaginaCheckActual,
          PaginaCheckParent, PaginaNoWo, PaginaCheck)
