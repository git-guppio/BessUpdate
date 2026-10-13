"""Modello Qt per visualizzare un DataFrame con colori, barrato, tooltip,
modifica in linea, filtro testuale/per esito e ordinamento."""
from __future__ import annotations

from typing import Callable

import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont

from conversione_sedi.gui.stile import stile_cella
from conversione_sedi.tabella import MetaRiga


def _testo(valore) -> str:
    if valore is None or (isinstance(valore, float) and pd.isna(valore)) or valore is pd.NA:
        return ""
    return str(valore)


class ModelloTabella(QAbstractTableModel):
    """Il modello non modifica i dati: emette modificaRichiesta e la pagina
    applica la modifica al progetto, poi ricarica il modello."""
    modificaRichiesta = Signal(int, str, str)          # riga, colonna, valore

    def __init__(self, parent=None):
        super().__init__(parent)
        self.df = pd.DataFrame()
        self.meta: list[MetaRiga] | None = None
        self.colonna_esito: str | None = None
        self.modificabili: set[str] = set()
        self.righe_manuali: set[int] = set()
        self.tooltip: Callable[[int, str], str | None] | None = None
        self._valori: list[list[str]] = []
        self._colonne: list[str] = []

    def imposta(self, df: pd.DataFrame, meta: list[MetaRiga] | None = None,
                colonna_esito: str | None = None, modificabili=(), righe_manuali=(),
                tooltip: Callable[[int, str], str | None] | None = None) -> None:
        self.beginResetModel()
        self.df = df.reset_index(drop=True)
        self.meta = meta
        self.colonna_esito = colonna_esito if colonna_esito in df.columns else None
        self.modificabili = set(modificabili)
        self.righe_manuali = set(righe_manuali)
        self.tooltip = tooltip
        self._colonne = [str(c) for c in self.df.columns]
        self._valori = [[_testo(v) for v in riga] for riga in self.df.itertuples(index=False)]
        self.endResetModel()

    # ------------------------------------------------------------------
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._valori)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._colonne)

    def headerData(self, sezione, orientamento, ruolo=Qt.DisplayRole):
        if ruolo == Qt.DisplayRole and orientamento == Qt.Horizontal:
            return self._colonne[sezione]
        return None

    def colonna(self, indice: int) -> str:
        return self._colonne[indice]

    def valore(self, riga: int, colonna: str) -> str:
        return self._valori[riga][self._colonne.index(colonna)]

    def meta_riga(self, riga: int) -> MetaRiga | None:
        return self.meta[riga] if self.meta else None

    def stile(self, riga: int, colonna: str):
        esito = self._valori[riga][self._colonne.index(self.colonna_esito)] if self.colonna_esito else None
        return stile_cella(self.meta_riga(riga), colonna, esito, riga in self.righe_manuali)

    def data(self, indice, ruolo=Qt.DisplayRole):
        if not indice.isValid():
            return None
        riga, colonna = indice.row(), self._colonne[indice.column()]
        if ruolo in (Qt.DisplayRole, Qt.EditRole):
            return self._valori[riga][indice.column()]
        if ruolo == Qt.ForegroundRole:
            s = self.stile(riga, colonna)
            return QBrush(QColor(s.testo)) if s.testo else None
        if ruolo == Qt.BackgroundRole:
            s = self.stile(riga, colonna)
            return QBrush(QColor(s.sfondo)) if s.sfondo else None
        if ruolo == Qt.FontRole:
            meta = self.meta_riga(riga)
            if meta is not None and meta.rimossa:
                font = QFont()
                font.setStrikeOut(True)
                return font
            return None
        if ruolo == Qt.ToolTipRole:
            meta = self.meta_riga(riga)
            if meta is not None and colonna in meta.originali:
                return f"Valore importato: {meta.originali[colonna] or '(vuoto)'}"
            if self.tooltip:
                return self.tooltip(riga, colonna)
        return None

    def flags(self, indice):
        base = super().flags(indice)
        if not indice.isValid():
            return base
        meta = self.meta_riga(indice.row())
        if self._colonne[indice.column()] in self.modificabili and not (meta and meta.rimossa):
            return base | Qt.ItemIsEditable
        return base

    def setData(self, indice, valore, ruolo=Qt.EditRole):
        if ruolo != Qt.EditRole or not indice.isValid():
            return False
        nuovo = "" if valore is None else str(valore)
        if nuovo != self._valori[indice.row()][indice.column()]:
            self.modificaRichiesta.emit(indice.row(), self._colonne[indice.column()], nuovo)
        return False


def _chiave_ordinamento(testo: str):
    t = testo.strip()
    return (0, float(t), "") if t.replace(".", "", 1).isdigit() else (1, 0.0, t.casefold())


class FiltroOrdinamento(QSortFilterProxyModel):
    """Filtro testuale su tutte le colonne + filtro per categoria di esito;
    ordinamento numerico per le colonne numeriche."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._testo = ""
        self._esito: str | None = None
        self._categoria: Callable[[str], str] = lambda v: v

    def _cambia_filtro(self, modifica: Callable[[], None]) -> None:
        if hasattr(self, "beginFilterChange"):              # Qt >= 6.9
            self.beginFilterChange()
            modifica()
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        else:
            modifica()
            self.invalidateFilter()

    def imposta_testo(self, testo: str) -> None:
        self._cambia_filtro(lambda: setattr(self, "_testo", testo.strip().casefold()))

    def imposta_esito(self, esito: str | None, categoria: Callable[[str], str] | None = None) -> None:
        def modifica():
            self._esito = esito or None
            if categoria:
                self._categoria = categoria
        self._cambia_filtro(modifica)

    def filterAcceptsRow(self, riga, parent):
        m: ModelloTabella = self.sourceModel()
        if self._esito and m.colonna_esito:
            if self._categoria(m.valore(riga, m.colonna_esito)) != self._esito:
                return False
        if self._testo:
            return any(self._testo in v.casefold() for v in m._valori[riga])
        return True

    def lessThan(self, sinistra, destra):
        m: ModelloTabella = self.sourceModel()
        a = m._valori[sinistra.row()][sinistra.column()]
        b = m._valori[destra.row()][destra.column()]
        return _chiave_ordinamento(a) < _chiave_ordinamento(b)
