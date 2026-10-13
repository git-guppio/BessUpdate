"""Aspetto dell'applicazione: tema chiaro fisso, indipendente dal tema di
Windows. I colori di origine ed esito (stile.py) sono pensati per uno sfondo
chiaro: con il tema scuro il testo bianco sarebbe illeggibile sugli sfondi
colorati."""
from PySide6.QtCore import Qt


def imposta_aspetto(app) -> None:
    app.setStyle("Fusion")
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)      # Qt >= 6.8
    except AttributeError:
        pass
    app.setPalette(app.style().standardPalette())                  # palette chiara di Fusion
