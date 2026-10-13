"""Pannello tabella comune a tutte le schede: pulsanti, ricerca, filtro per
esito, tabella ordinabile, menu contestuale, copia negli appunti, esportazione."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import pandas as pd
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QCompleter, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMenu, QPushButton, QStyledItemDelegate, QTableView, QVBoxLayout, QWidget,
)

from conversione_sedi.esportazione import esporta_excel, testo_tabulato
from conversione_sedi.gui.modello import FiltroOrdinamento, ModelloTabella

TUTTI = "Tutti gli esiti"


class DelegatoCompletamento(QStyledItemDelegate):
    """Editor con completamento automatico (es. codici di New)."""

    def __init__(self, parole: Callable[[], list[str]], parent=None):
        super().__init__(parent)
        self._parole = parole

    def createEditor(self, parent, opzioni, indice):
        editor = QLineEdit(parent)
        completamento = QCompleter(self._parole(), editor)
        completamento.setCaseSensitivity(Qt.CaseInsensitive)
        completamento.setFilterMode(Qt.MatchContains)
        editor.setCompleter(completamento)
        return editor


class PannelloTabella(QWidget):
    def __init__(self, nome_esportazione: str, parent=None):
        super().__init__(parent)
        self.nome_esportazione = nome_esportazione
        self.cartella_esportazione: Callable[[], str] = lambda: ""
        self.azioni_contestuali: Callable[[list[int], str | None], list[QAction | None]] | None = None
        self.categoria_esito: Callable[[str], str] = lambda v: v
        self._riga_menu: int | None = None
        self._colonna_menu: str | None = None

        self.modello = ModelloTabella(self)
        self.proxy = FiltroOrdinamento(self)
        self.proxy.setSourceModel(self.modello)

        self.vista = QTableView(self)
        self.vista.setModel(self.proxy)
        self.vista.setSortingEnabled(True)
        self.vista.sortByColumn(-1, Qt.AscendingOrder)
        self.vista.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.vista.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.vista.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.vista.setAlternatingRowColors(False)
        self.vista.verticalHeader().setDefaultSectionSize(22)
        self.vista.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.vista.horizontalHeader().setStretchLastSection(True)
        self.vista.setContextMenuPolicy(Qt.CustomContextMenu)
        self.vista.customContextMenuRequested.connect(self._menu)

        self.barra = QHBoxLayout()
        self.barra.setContentsMargins(0, 0, 0, 0)
        self.pulsante_esporta = QPushButton("Esporta")
        self.pulsante_esporta.clicked.connect(self.esporta)
        self.esito = QComboBox()
        self.esito.setMinimumWidth(180)
        self.esito.setVisible(False)
        self.esito.currentTextChanged.connect(self._filtro_esito)
        self.ricerca = QLineEdit()
        self.ricerca.setPlaceholderText("Cerca…")
        self.ricerca.setClearButtonEnabled(True)
        self.ricerca.setMaximumWidth(260)
        self.ricerca.textChanged.connect(self.proxy.imposta_testo)
        self.ricerca.textChanged.connect(lambda _: self._aggiorna_conteggio())
        self.barra.addStretch(1)
        self.barra.addWidget(self.pulsante_esporta)
        self.barra.addSpacing(12)
        self.barra.addWidget(self.esito)
        self.barra.addWidget(self.ricerca)

        self.info = QLabel()
        self.info.setStyleSheet("color: #555;")
        self.conteggio = QLabel()
        self.conteggio.setStyleSheet("color: #555;")
        riga_info = QHBoxLayout()
        riga_info.addWidget(self.info, 1)
        riga_info.addWidget(self.conteggio)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.barra)
        layout.addWidget(self.vista, 1)
        layout.addLayout(riga_info)

        copia = QAction(self)
        copia.setShortcut(QKeySequence.Copy)
        copia.triggered.connect(self.copia_selezione)
        self.vista.addAction(copia)

    # ------------------------------------------------------------------
    # Configurazione
    # ------------------------------------------------------------------
    def aggiungi_pulsante(self, testo: str, azione: Callable[[], None]) -> QPushButton:
        pulsante = QPushButton(testo)
        pulsante.clicked.connect(azione)
        self.barra.insertWidget(self.barra.count() - 5, pulsante)   # prima dello spazio flessibile
        return pulsante

    def imposta_esiti(self, esiti: list[str] | None, categoria: Callable[[str], str] | None = None) -> None:
        """Valori del filtro per esito (None = filtro nascosto)."""
        if categoria:
            self.categoria_esito = categoria
        corrente = self.esito.currentText()
        self.esito.blockSignals(True)
        self.esito.clear()
        if esiti:
            self.esito.addItems([TUTTI, *esiti])
            if corrente in esiti:
                self.esito.setCurrentText(corrente)
        self.esito.blockSignals(False)
        self.esito.setVisible(bool(esiti))
        self._filtro_esito(self.esito.currentText())

    def seleziona_esito(self, esito: str) -> None:
        self.esito.setCurrentText(esito)

    def _filtro_esito(self, testo: str) -> None:
        self.proxy.imposta_esito(None if testo in ("", TUTTI) else testo, self.categoria_esito)
        self._aggiorna_conteggio()

    def imposta_dati(self, df: pd.DataFrame, **opzioni) -> None:
        larghezze = {self.modello.colonna(i): self.vista.columnWidth(i)
                     for i in range(self.modello.columnCount())}
        primo = self.modello.columnCount() == 0
        self.modello.imposta(df, **opzioni)
        if primo:
            self.vista.resizeColumnsToContents()
            for i in range(self.modello.columnCount()):
                self.vista.setColumnWidth(i, min(self.vista.columnWidth(i) + 12, 380))
        else:
            for i in range(self.modello.columnCount()):
                nome = self.modello.colonna(i)
                if nome in larghezze:
                    self.vista.setColumnWidth(i, larghezze[nome])
        self._aggiorna_conteggio()

    def _aggiorna_conteggio(self) -> None:
        totale, visibili = self.modello.rowCount(), self.proxy.rowCount()
        self.conteggio.setText(f"{totale:,} righe".replace(",", ".") if totale == visibili
                               else f"{visibili:,} di {totale:,} righe".replace(",", "."))

    # ------------------------------------------------------------------
    # Selezione
    # ------------------------------------------------------------------
    def righe_selezionate(self) -> list[int]:
        """Righe selezionate, come indici del modello (non del filtro)."""
        righe = {self.proxy.mapToSource(i).row() for i in self.vista.selectionModel().selectedRows()}
        return sorted(righe)

    def _righe_visibili(self) -> list[int]:
        return [self.proxy.mapToSource(self.proxy.index(r, 0)).row() for r in range(self.proxy.rowCount())]

    def _df(self, righe: list[int]) -> pd.DataFrame:
        return self.modello.df.iloc[righe] if righe else self.modello.df.iloc[0:0]

    # ------------------------------------------------------------------
    # Appunti
    # ------------------------------------------------------------------
    def _negli_appunti(self, testo: str) -> None:
        QGuiApplication.clipboard().setText(testo)

    def copia_tabella(self) -> None:
        self._negli_appunti(testo_tabulato(self._df(self._righe_visibili())))

    def copia_selezione(self) -> None:
        righe = self.righe_selezionate()
        if righe:
            self._negli_appunti(testo_tabulato(self._df(righe)))

    def copia_riga(self, riga: int) -> None:
        self._negli_appunti(testo_tabulato(self._df([riga])))

    def copia_cella(self, riga: int, colonna: str) -> None:
        self._negli_appunti(self.modello.valore(riga, colonna))

    # ------------------------------------------------------------------
    # Menu contestuale
    # ------------------------------------------------------------------
    def _menu(self, punto: QPoint) -> None:
        indice = self.vista.indexAt(punto)
        riga = self.proxy.mapToSource(indice).row() if indice.isValid() else None
        colonna = self.modello.colonna(indice.column()) if indice.isValid() else None
        if riga is not None and riga not in self.righe_selezionate():
            self.vista.selectRow(indice.row())
        selezionate = self.righe_selezionate()

        menu = QMenu(self)
        if self.azioni_contestuali:
            azioni = self.azioni_contestuali(selezionate, colonna)
            for azione in azioni:
                if azione is None:
                    menu.addSeparator()
                else:
                    azione.setParent(menu)
                    menu.addAction(azione)
            if azioni:
                menu.addSeparator()
        menu.addAction("Copia tabella", self.copia_tabella)
        a = menu.addAction("Copia righe selezionate", self.copia_selezione)
        a.setEnabled(bool(selezionate))
        a = menu.addAction("Copia riga", lambda: self.copia_riga(riga))
        a.setEnabled(riga is not None)
        a = menu.addAction("Copia cella", lambda: self.copia_cella(riga, colonna))
        a.setEnabled(riga is not None)
        menu.exec(self.vista.viewport().mapToGlobal(punto))

    # ------------------------------------------------------------------
    # Esportazione
    # ------------------------------------------------------------------
    def esporta(self) -> None:
        cartella = self.cartella_esportazione() or str(Path.home())
        percorso, _ = QFileDialog.getSaveFileName(
            self, "Esporta in Excel", str(Path(cartella) / f"{self.nome_esportazione}.xlsx"),
            "File Excel (*.xlsx)")
        if not percorso:
            return
        righe = self._righe_visibili()
        df = self._df(righe)
        esporta_excel(df, percorso, self.nome_esportazione,
                      lambda i, colonna: self.modello.stile(righe[i], colonna))
        self.window().statusBar().showMessage(f"Esportato: {percorso}", 8000)
