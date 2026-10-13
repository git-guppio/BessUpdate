from pathlib import Path

import pytest

from conversione_sedi.lista_sap import (
    ErroreListaSAP, avvisi_da_iw29, contiene_stato, leggi_lista_sap, ordini_da_iw39, sedi_da_ih06,
)

DATI = Path(__file__).parent / "dati"


def esempio(nome):
    return (DATI / nome).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Esempi reali esportati da SAP
# ---------------------------------------------------------------------------
def test_ih06():
    df = sedi_da_ih06(esempio("TestoAppunti_IH06.txt"))
    assert list(df.columns) == ["Sede tecnica", "Descrizione"]
    assert len(df) == 1782
    assert df.iloc[0].tolist() == ["USE-USS5", "BESS @ Fencepost"]
    assert df.iloc[-1].tolist() == ["USE-USS5-4E-MV-SG-VT", "MV M&P Transformer - Voltage Transformer"]
    # le virgolette fanno parte della descrizione in SAP
    assert '"Buildings, Areas and Roads"' in set(df["Descrizione"])


def test_iw39():
    df = ordini_da_iw39(esempio("TestoAppunti_IW39.txt"))
    assert list(df.columns) == ["Sede tecnica", "Work Order", "Descrizione", "Stato"]
    assert len(df) == 15
    assert df.iloc[0].tolist() == ["USE-USS5-00-OC", "210001737613", "BOP_Monthly_SPCC",
                                   "RIL. CONP CALP KKMP NLIA"]


def test_iw29():
    df = avvisi_da_iw29(esempio("TestoAppunti_IW29.txt"))
    assert list(df.columns) == ["Sede tecnica", "Notification", "Descrizione", "Stato"]
    assert df["Notification"].tolist() == ["1100110930", "1200927446", "1200902385"]
    assert df.loc[2, "Sede tecnica"] == "USE-USS5-1E-02-C1"


# ---------------------------------------------------------------------------
# Casi particolari
# ---------------------------------------------------------------------------
def riga(*valori, larghezze=(16, 32, 12)):
    return "|" + "|".join(f"{v:<{w}}" for v, w in zip(valori, larghezze)) + "|"


INTESTAZIONE_IH06 = riga("  Sede tecnica", "Definizione della sede tecnica", "St.sist.")
TESTO_IH06 = "\n".join([
    "13.10.26 Visualizzazione lista dinamica       1",
    "-" * 60,
    INTESTAZIONE_IH06,
    "-" * 60,
    riga("  ITE-A", "Uno", "CRT"),
    riga("  ITE-A-01", "Due | con barra", "CRT INAT"),
    riga("  ITE-A-02", "Tre", "CRT CANC"),
    riga("  ITE-A-03", "Quattro", "OGIN"),
    riga("  ITE-A-05", "Sei", "FCAN CRT"),
    riga("  ITE-A-06", "Sette", "CANCX"),
    "-" * 60,
    "13.10.26 Visualizzazione lista dinamica       2",   # cambio pagina
    INTESTAZIONE_IH06,
    "-" * 60,
    riga("  ITE-A-04", "Cinque", "DLFL"),
]) + "\n"


def test_separatore_nei_dati_e_intestazione_ripetuta():
    df = leggi_lista_sap(TESTO_IH06)
    assert len(df) == 7                                     # intestazione ripetuta ignorata
    assert df.loc[1, "Definizione della sede tecnica"] == "Due | con barra"


def test_filtro_stati_esclusi():
    df = sedi_da_ih06(TESTO_IH06)
    # esclusi CANC, OGIN, FCAN; lo stato deve comparire come voce a sé ("CANCX" non è "CANC")
    assert df["Sede tecnica"].tolist() == ["ITE-A", "ITE-A-01", "ITE-A-06", "ITE-A-04"]


@pytest.mark.parametrize("stati, atteso", [
    ("CANC", True), ("CRT CANC", True), ("CANC CRT", True), ("CANCX", False), ("", False),
])
def test_contiene_stato(stati, atteso):
    assert contiene_stato(stati, "CANC") is atteso


def test_testo_senza_lista():
    with pytest.raises(ErroreListaSAP, match="Nessuna lista"):
        leggi_lista_sap("Non sono stati selezionati oggetti")


def test_layout_modificato():
    testo = "|Sede tecnica|Altro|\n|ITE-A|x|\n"
    with pytest.raises(ErroreListaSAP, match="Definizione della sede tecnica.*Verificare il layout"):
        sedi_da_ih06(testo)


def test_lista_vuota():
    testo = "|Ordine|Descrizione|Sede tecnica|Stato sistema|\n------\n"
    assert ordini_da_iw39(testo).empty
