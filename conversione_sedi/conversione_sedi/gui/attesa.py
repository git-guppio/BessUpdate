"""Esecuzione di un'operazione lunga (estrazione SAP) in un thread separato,
con una finestra di attesa modale che mostra il tempo trascorso."""
from __future__ import annotations

import sys
import time
from typing import Any, Callable

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QVBoxLayout


class _Lavoro(QThread):
    riuscito = Signal(object)
    fallito = Signal(object)

    def __init__(self, funzione: Callable[[], Any], parent=None):
        super().__init__(parent)
        self._funzione = funzione

    def run(self):
        debugger = sys.modules.get("debugpy")   # avvio dal debugger di VS Code:
        if debugger is not None:                # abilita i breakpoint in questo thread
            debugger.debug_this_thread()
        com = None
        try:
            import pythoncom                    # SAP GUI Scripting usa COM: va inizializzato nel thread
            pythoncom.CoInitialize()
            com = pythoncom
        except ImportError:
            pass
        try:
            self.riuscito.emit(self._funzione())
        except Exception as e:                  # gestito dal chiamante
            self.fallito.emit(e)
        finally:
            if com:
                com.CoUninitialize()


class FinestraAttesa(QDialog):
    def __init__(self, titolo: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Operazione in corso")
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setModal(True)
        self._inizio = time.monotonic()
        self._etichetta = QLabel(titolo)
        self._tempo = QLabel("0 s")
        barra = QProgressBar()
        barra.setRange(0, 0)                    # indeterminata
        layout = QVBoxLayout(self)
        layout.addWidget(self._etichetta)
        layout.addWidget(barra)
        layout.addWidget(self._tempo)
        self.setMinimumWidth(360)
        self._timer = QTimer(self)
        self._timer.timeout.connect(lambda: self._tempo.setText(f"{int(time.monotonic() - self._inizio)} s"))
        self._timer.start(500)

    def reject(self):                           # Esc non interrompe SAP
        pass


def esegui_con_attesa(parent, titolo: str, funzione: Callable[[], Any]) -> Any:
    """Esegue funzione() in un thread mostrando la finestra di attesa.
    Restituisce il risultato o rilancia l'eccezione sollevata da funzione()."""
    esito: dict[str, Any] = {}
    dialogo = FinestraAttesa(titolo, parent)
    lavoro = _Lavoro(funzione, parent)
    lavoro.riuscito.connect(lambda r: esito.setdefault("risultato", r))
    lavoro.fallito.connect(lambda e: esito.setdefault("errore", e))
    lavoro.finished.connect(dialogo.accept)
    lavoro.start()
    dialogo.exec()
    lavoro.wait()
    if "errore" in esito:
        raise esito["errore"]
    return esito.get("risultato")
