"""Avvio dell'interfaccia grafica: python -m conversione_sedi.gui"""
import sys
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox

from conversione_sedi.gui.finestra import Finestra
from conversione_sedi.nucleo import ErroreConfigurazione
from conversione_sedi.progetto import ErroreProgetto, Progetto, ultimo_progetto


def _errore_imprevisto(tipo, valore, tb):
    testo = "".join(traceback.format_exception(tipo, valore, tb))
    finestra = QMessageBox(QMessageBox.Critical, "Errore imprevisto", f"{tipo.__name__}: {valore}")
    finestra.setDetailedText(testo)
    finestra.exec()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("BESS Update")
    app.setStyle("Fusion")
    sys.excepthook = _errore_imprevisto

    try:
        progetto = Progetto()
    except ErroreConfigurazione as e:
        QMessageBox.critical(None, "Regole di conversione non valide", "\n".join(e.errori))
        return 1

    ultimo = ultimo_progetto()
    avviso = None
    if ultimo:
        try:
            progetto = Progetto.apri(ultimo)
        except (ErroreProgetto, ErroreConfigurazione) as e:
            avviso = str(e)

    finestra = Finestra(progetto)
    finestra.show()
    if avviso:
        finestra.errore(f"Impossibile riaprire l'ultimo progetto: {avviso}")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
