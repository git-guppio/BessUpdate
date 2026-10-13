from pathlib import Path

import pandas as pd
import pytest

from conversione_sedi.lista_sap import sedi_da_ih06
from conversione_sedi.verifica import COL_ESITO, verifica

DATI = Path(__file__).parent / "dati"


def tabella(*righe):
    return pd.DataFrame(list(righe), columns=["Sede tecnica", "Descrizione"])


def esiti(v):
    return dict(zip(v.dati["Sede tecnica"], v.dati[COL_ESITO]))


def test_esiti():
    sap = tabella(("USE-USS5", "Impianto"),
                  ("USE-USS5-1E", "Area 1"),
                  ("USE-USS5-1E-01", "  Linea   1 "),
                  ("USE-USS5-1E-02", "linea 2"),
                  ("USE-USS5-00-VC", '"Buildings, Areas and Roads"'),
                  ("USE-USS5-OLD", "Vecchia"))
    new = tabella(("USE-USS5-1E", "Area 1"),
                  ("USE-USS5-1E-01", "Linea 1"),
                  ("USE-USS5-1E-02", "Linea 2"),
                  ("USE-USS5-00-VC", "Buildings, Areas and Roads"),
                  ("USE-USS5-1E-03", "Linea 3"))
    v = verifica(sap, new)
    assert esiti(v) == {
        "USE-USS5": "Esclusa (livello 1-2)",
        "USE-USS5-1E": "Allineata",
        "USE-USS5-1E-01": "Allineata",                                     # spazi ignorati
        "USE-USS5-1E-02": 'Descrizione diversa (New: "Linea 2")',          # maiuscole contano
        "USE-USS5-00-VC": 'Descrizione diversa (New: "Buildings, Areas and Roads")',  # virgolette contano
        "USE-USS5-OLD": "In eccesso in SAP",
        "USE-USS5-1E-03": "Mancante in SAP",
    }
    # le mancanti sono in fondo, con codice e descrizione di New
    assert v.dati.iloc[-1].tolist() == ["USE-USS5-1E-03", "Linea 3", "Mancante in SAP"]
    assert v.dati.iloc[0, 1] == "Impianto"                                 # descrizione SAP originale

    assert v.conteggi() == {"Allineata": 2, "Mancante in SAP": 1, "In eccesso in SAP": 1,
                            "Descrizione diversa": 2, "Esclusa (livello 1-2)": 1}
    assert v.totale == 6
    assert v.percentuali()["Allineata"] == 33.3
    assert v.allineamento == 33.3 and not v.allineato
    assert v.filtra("Descrizione diversa")["Sede tecnica"].tolist() == ["USE-USS5-1E-02", "USE-USS5-00-VC"]


def test_allineato():
    t = tabella(("USE-USS5-1E", "Area 1"), ("USE-USS5-1E-01", "Linea 1"))
    v = verifica(t, t)
    assert v.allineato and v.allineamento == 100.0


def test_niente_da_confrontare():
    v = verifica(tabella(("USE-USS5", "Impianto")), tabella())
    assert v.totale == 0 and v.allineamento == 100.0 and v.allineato


def test_normalizzazione_e_duplicati():
    sap = tabella((" use-uss5-1e ", "Area"), ("USE-USS5-1E", "Altro"))
    new = tabella(("USE-USS5-1E", "Area"))
    v = verifica(sap, new)
    assert esiti(v) == {"USE-USS5-1E": "Allineata"}
    assert any(a.startswith("SAP: Sedi tecniche duplicate") for a in v.avvisi)


def test_con_estrazione_reale_ih06():
    sap = sedi_da_ih06((DATI / "TestoAppunti_IH06.txt").read_text(encoding="utf-8"))
    v = verifica(sap, sap)
    assert v.allineato and v.totale == len(sap)    # impianto presente in entrambi: confrontato
    v = verifica(sap, sap.iloc[1:])
    assert v.allineato and v.totale == len(sap) - 1  # impianto solo in SAP: escluso


def test_colonna_mancante():
    with pytest.raises(KeyError, match="New"):
        verifica(tabella(("A-B-C", "x")), pd.DataFrame({"Sede tecnica": ["A-B-C"]}))
