import pandas as pd
import pytest

from conversione_sedi.ingresso_uscita import ErroreDati
from conversione_sedi.nuova_codifica import (
    appartiene, carica_new, impianto_di, valida_new, verifica_impianto,
)


def crea_excel(percorso, righe, colonne=("Sede tecnica", "Descrizione")):
    pd.DataFrame(righe, columns=list(colonne)).to_excel(percorso, index=False)
    return percorso


def test_caricamento_corretto(tmp_path):
    p = crea_excel(tmp_path / "new.xlsx", [
        ("USE", "Radice"),
        ("USE-USS5", "Impianto"),
        (" use-uss5-1e ", "  Area 1 "),
        ("", ""),                                  # riga vuota: ignorata
        ("USE-USS5-1E-01", "01"),                  # "01" resta testo
        ("", "descrizione orfana"),
    ])
    n = carica_new(p)
    assert n.impianto == "USE-USS5"
    assert n.dati.values.tolist() == [["USE", "Radice"], ["USE-USS5", "Impianto"],
                                      ["USE-USS5-1E", "Area 1"], ["USE-USS5-1E-01", "01"]]
    assert n.avvisi == ["new.xlsx: righe con descrizione ma senza Sede tecnica, ignorate: 7."]


def test_intestazioni_flessibili_e_colonne_extra():
    df = pd.DataFrame({"Note": ["x"], " SEDE_TECNICA ": ["USE-USS5-1E"], "descrizione": ["A"]})
    assert valida_new(df).dati.values.tolist() == [["USE-USS5-1E", "A"]]


def test_colonna_mancante():
    with pytest.raises(ErroreDati) as e:
        valida_new(pd.DataFrame({"Sede tecnica": ["USE-USS5-1E"], "Testo": ["A"]}))
    assert "colonna \"Descrizione\" mancante" in str(e.value)
    assert "Colonne presenti: \"Sede tecnica\", \"Testo\"" in str(e.value)


def test_duplicati_bloccanti(tmp_path):
    p = crea_excel(tmp_path / "new.xlsx", [("USE-USS5-1E", "A"), ("USE-USS5-1F", "B"),
                                           ("use-uss5-1e", "C")])
    with pytest.raises(ErroreDati) as e:
        carica_new(p)
    assert e.value.errori == ["new.xlsx: Sedi tecniche duplicate:",
                              "USE-USS5-1E ripetuta alle righe 2, 4."]


def test_impianto_unico_bloccante(tmp_path):
    p = crea_excel(tmp_path / "new.xlsx", [("USE-USS5-1E", "A"), ("USE-USS5-1F", "B"),
                                           ("USE-USS6-1E", "C"), ("ITE", "D")])
    with pytest.raises(ErroreDati) as e:
        carica_new(p)
    assert e.value.errori == ["new.xlsx: la lista deve riguardare un solo impianto:",
                              "Riga 4: USE-USS6-1E non appartiene all'impianto USE-USS5.",
                              "Riga 5: ITE non appartiene all'impianto USE-USS5."]


def test_elenco_errori_limitato():
    sedi = ["USE-USS5-1E"] * 2 + [f"USE-X{i}-1E" for i in range(30)]
    _, errori = verifica_impianto(sedi, impianto="USE-USS5")
    assert len(errori) == 21 and errori[-1] == "... e altre 10."


def test_file_vuoto_di_sedi():
    with pytest.raises(ErroreDati, match="nessuna Sede tecnica"):
        valida_new(pd.DataFrame({"Sede tecnica": ["", None], "Descrizione": ["", ""]}))


def test_impianto_non_determinabile():
    with pytest.raises(ErroreDati, match="Impossibile determinare l'impianto"):
        valida_new(pd.DataFrame({"Sede tecnica": ["USE"], "Descrizione": ["Radice"]}))


@pytest.mark.parametrize("sede, atteso", [
    ("USE", True), ("USE-USS5", True), ("USE-USS5-1E-01", True),
    ("ITE", False), ("USE-USS6", False), ("USE-USS50-1E", False),
])
def test_appartiene(sede, atteso):
    assert appartiene(sede, "USE-USS5") is atteso
    assert impianto_di("USE-USS5-1E") == "USE-USS5" and impianto_di("USE") == ""
