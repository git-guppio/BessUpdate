"""Conversione Sedi tecniche -> Nuove Sedi tecniche."""
from conversione_sedi.ingresso_uscita import (
    ErroreDati,
    EsitoElaborazione,
    converti_file,
    elabora,
    leggi_sedi,
    scrivi_output,
)
from conversione_sedi.nucleo import (
    Configurazione,
    ErroreConfigurazione,
    carica_configurazione,
    converti,
    elabora_dataframe,
    riepilogo,
)

__version__ = "1.0.0"
