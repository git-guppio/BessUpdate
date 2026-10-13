"""Finestra principale: barra laterale a passi, schede, menu e barra di stato."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QStackedWidget, QWidget,
)

from conversione_sedi.gui.pagine import PAGINE
from conversione_sedi.progetto import ESTENSIONE, Progetto, StatoScheda

ICONE = {
    StatoScheda.BLOCCATA: "🔒",
    StatoScheda.DA_ESEGUIRE: "○",
    StatoScheda.AGGIORNATA: "✓",
    StatoScheda.DA_AGGIORNARE: "⚠",
}
COLORI_STATO = {
    StatoScheda.BLOCCATA: "#9AA0A6",
    StatoScheda.DA_ESEGUIRE: "#333333",
    StatoScheda.AGGIORNATA: "#1E7B34",
    StatoScheda.DA_AGGIORNARE: "#B26A00",
}


class Finestra(QMainWindow):
    def __init__(self, progetto: Progetto):
        super().__init__()
        self.progetto = progetto
        self._cartella = str(progetto.percorso.parent) if progetto.percorso else str(Path.home())
        self.resize(1400, 820)

        self.passi = QListWidget()
        self.passi.setFixedWidth(210)
        self.passi.setIconSize(QSize(0, 0))
        font = QFont()
        font.setPointSize(10)
        self.passi.setFont(font)
        self.passi.setStyleSheet("QListWidget::item { padding: 8px 6px; }")
        self.pila = QStackedWidget()
        self.pagine = []
        for classe in PAGINE:
            pagina = classe(self)
            self.pagine.append(pagina)
            self.pila.addWidget(pagina)
            self.passi.addItem(QListWidgetItem())
        self.passi.currentRowChanged.connect(self._cambia_pagina)

        centrale = QWidget()
        layout = QHBoxLayout(centrale)
        layout.addWidget(self.passi)
        layout.addWidget(self.pila, 1)
        self.setCentralWidget(centrale)

        self.stato_salvataggio = QLabel()
        self.statusBar().addPermanentWidget(self.stato_salvataggio)
        self._menu()
        self.passi.setCurrentRow(0)
        self.aggiorna()

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------
    def _menu(self) -> None:
        file = self.menuBar().addMenu("&File")
        for testo, scorciatoia, funzione in (
            ("&Nuovo progetto", QKeySequence.New, self.nuovo),
            ("&Apri progetto…", QKeySequence.Open, self.apri),
            ("Salva progetto &con nome…", QKeySequence("Ctrl+Shift+S"), self.salva_con_nome),
        ):
            azione = QAction(testo, self)
            azione.setShortcut(scorciatoia)
            azione.triggered.connect(funzione)
            file.addAction(azione)
        file.addSeparator()
        file.addAction("&Esci", self.close)
        aiuto = self.menuBar().addMenu("&?")
        aiuto.addAction("Informazioni", lambda: self.informa(
            "BESS Update", "Allineamento delle Sedi tecniche SAP alla nuova codifica.\n\n"
            "Regole di conversione: config/regole.csv e config/trasformazioni.csv."))

    # ------------------------------------------------------------------
    # Aggiornamento
    # ------------------------------------------------------------------
    def aggiorna(self) -> None:
        p = self.progetto
        for i, pagina in enumerate(self.pagine):
            stato = p.stato(pagina.scheda)
            voce = self.passi.item(i)
            voce.setText(f"{i + 1}  {ICONE[stato]}  {pagina.scheda.value}")
            voce.setForeground(QColor(COLORI_STATO[stato]))
            voce.setToolTip(stato.value)
        self.pila.currentWidget().aggiorna()

        nome = p.percorso.name if p.percorso else "progetto non salvato"
        impianto = f" — {p.impianto}" if p.impianto else ""
        self.setWindowTitle(f"BESS Update — {nome}{impianto}")
        if p.percorso and p.percorso.is_file():
            ora = datetime.fromtimestamp(p.percorso.stat().st_mtime).strftime("%H:%M:%S")
            self.stato_salvataggio.setText(f"Salvato automaticamente alle {ora}  ")
        elif p._ha_dati():
            self.stato_salvataggio.setText("Progetto non salvato: File > Salva progetto con nome  ")
        else:
            self.stato_salvataggio.setText("")

    def _cambia_pagina(self, riga: int) -> None:
        if riga < 0:
            return
        self.pila.setCurrentIndex(riga)
        self.pagine[riga].aggiorna()

    # ------------------------------------------------------------------
    # Progetto
    # ------------------------------------------------------------------
    def cartella_lavoro(self) -> str:
        return self._cartella

    def _imposta_progetto(self, progetto: Progetto) -> None:
        self.progetto = progetto
        if progetto.percorso:
            self._cartella = str(progetto.percorso.parent)
        self.passi.setCurrentRow(0)
        self.aggiorna()

    def nuovo(self) -> None:
        if self.progetto._ha_dati() and not self.conferma(
                "Creare un nuovo progetto?\n"
                + ("Il progetto attuale resta salvato nel suo file." if self.progetto.percorso
                   else "Il progetto attuale non è salvato e andrà perso.")):
            return
        try:
            self._imposta_progetto(Progetto())
        except Exception as e:
            self.errore(e)

    def apri(self) -> None:
        percorso, _ = QFileDialog.getOpenFileName(self, "Apri progetto", self._cartella,
                                                  f"Progetto BESS (*{ESTENSIONE})")
        if not percorso:
            return
        try:
            self._imposta_progetto(Progetto.apri(percorso))
        except Exception as e:
            self.errore(e)

    def salva_con_nome(self, cartella: str | None = None, nome: str | None = None) -> bool:
        proposta = Path(cartella or self._cartella) / f"{nome or self.progetto.impianto or 'progetto'}{ESTENSIONE}"
        percorso, _ = QFileDialog.getSaveFileName(self, "Salva progetto", str(proposta),
                                                  f"Progetto BESS (*{ESTENSIONE})")
        if not percorso:
            return False
        try:
            self.progetto.salva(percorso)
            self._cartella = str(Path(percorso).parent)
        except Exception as e:
            self.errore(e)
            return False
        self.aggiorna()
        return True

    def assicura_percorso(self, cartella: Path, nome: str) -> None:
        """Al primo caricamento chiede dove salvare il progetto (salvataggio automatico)."""
        if self.progetto.percorso is None:
            self.informa("Salvataggio del progetto",
                         "Scegliere il file del progetto: da questo momento ogni modifica "
                         "verrà salvata automaticamente.")
            self.salva_con_nome(str(cartella), nome)

    def closeEvent(self, evento) -> None:
        if self.progetto.percorso is None and self.progetto._ha_dati():
            risposta = QMessageBox.question(
                self, "Progetto non salvato", "Il progetto non è mai stato salvato. Salvarlo prima di uscire?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            if risposta == QMessageBox.Cancel or (risposta == QMessageBox.Save and not self.salva_con_nome()):
                evento.ignore()
                return
        evento.accept()

    # ------------------------------------------------------------------
    # Messaggi
    # ------------------------------------------------------------------
    def errore(self, e) -> None:
        righe = getattr(e, "errori", None)
        testo = "\n".join(righe) if righe else str(e)
        if not isinstance(e, str) and type(e).__name__ not in (
                "ErroreDati", "ErroreConfigurazione", "ErroreProgetto", "ImpiantoDiverso",
                "ErroreModifica", "ErroreSAP", "ErroreListaSAP"):
            testo = f"Errore imprevisto ({type(e).__name__}): {testo}"
        finestra = QMessageBox(QMessageBox.Warning, "Attenzione", testo.split("\n")[0], QMessageBox.Ok, self)
        if righe and len(righe) > 1:
            finestra.setInformativeText("\n".join(righe[1:12]) + ("\n…" if len(righe) > 12 else ""))
            finestra.setDetailedText(testo)
        finestra.exec()

    def informa(self, titolo: str, testo: str) -> None:
        QMessageBox.information(self, titolo, testo)

    def conferma(self, testo: str) -> bool:
        return QMessageBox.question(self, "Conferma", testo) == QMessageBox.Yes

    def chiedi_conserva(self, n: int, dove: str) -> bool | None:
        """True = conserva, False = scarta, None = annulla."""
        finestra = QMessageBox(QMessageBox.Question, "Modifiche manuali",
                               f"Sono presenti {n} modifiche manuali in {dove}.\n"
                               "Conservarle con i nuovi dati?", parent=self)
        conserva = finestra.addButton("Conserva", QMessageBox.YesRole)
        scarta = finestra.addButton("Scarta", QMessageBox.NoRole)
        finestra.addButton("Annulla", QMessageBox.RejectRole)
        finestra.setDefaultButton(conserva)
        finestra.exec()
        if finestra.clickedButton() is conserva:
            return True
        if finestra.clickedButton() is scarta:
            return False
        return None
