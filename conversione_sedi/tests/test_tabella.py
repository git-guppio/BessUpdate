import pandas as pd
import pytest

from conversione_sedi.riconciliazione import normalizza_sede
from conversione_sedi.tabella import ErroreModifica, Tabella

COLONNE = ("Sede tecnica", "Descrizione")


def df(*righe):
    return pd.DataFrame(list(righe), columns=list(COLONNE))


def nuova(valida=None):
    t = Tabella(COLONNE, normalizza={"Sede tecnica": normalizza_sede}, valida=valida)
    t.imposta_base(df(("P-I-A", "Uno"), ("p-i-b ", "Due"), ("P-I-A", "Duplicato")))
    return t


def chiave(t, sede):
    vista, meta = t.vista()
    return meta[vista.index[vista["Sede tecnica"] == sede][0]].chiave


def test_base():
    t = nuova()
    assert t.dati().values.tolist() == [["P-I-A", "Uno"], ["P-I-B", "Due"]]   # normalizzata, senza duplicati
    vista, meta = t.vista()
    assert vista["Origine"].tolist() == ["IMPORTATO", "IMPORTATO"]
    assert t.conta_modifiche() == 0 and not t.vuota


def test_modifica_cella_e_ripristino():
    t = nuova()
    k = chiave(t, "P-I-A")
    t.modifica(k, "Descrizione", "Uno bis")
    vista, meta = t.vista()
    assert vista.loc[0, "Descrizione"] == "Uno bis" and vista.loc[0, "Origine"] == "MODIFICATO"
    assert meta[0].originali == {"Descrizione": "Uno"}            # per il tooltip
    t.ripristina_cella(k, "Descrizione")
    assert t.vista()[0].loc[0, "Origine"] == "IMPORTATO"
    t.modifica(k, "Descrizione", "Uno bis")
    t.modifica(k, "Descrizione", "Uno")                          # tornata al valore importato
    assert t.conta_modifiche() == 0


def test_modifica_chiave_univoca():
    t = nuova()
    with pytest.raises(ErroreModifica, match="già presente: P-I-B"):
        t.modifica(chiave(t, "P-I-A"), "Sede tecnica", "p-i-b")
    t.modifica(chiave(t, "P-I-A"), "Sede tecnica", "p-i-c")      # normalizzata
    assert t.dati()["Sede tecnica"].tolist() == ["P-I-C", "P-I-B"]
    with pytest.raises(ErroreModifica, match="obbligatorio"):
        t.modifica(chiave(t, "P-I-B"), "Sede tecnica", "  ")


def test_validazione_specifica():
    t = nuova(valida=lambda v: [] if v["Sede tecnica"].startswith("P-I") else ["Impianto diverso."])
    with pytest.raises(ErroreModifica, match="Impianto diverso"):
        t.aggiungi({"Sede tecnica": "Q-I-A"})


def test_righe_rimosse_e_aggiunte():
    t = nuova()
    k = chiave(t, "P-I-A")
    t.rimuovi(k)
    vista, meta = t.vista()
    assert vista.loc[0, "Origine"] == "RIMOSSO" and meta[0].rimossa       # resta visibile
    assert t.dati()["Sede tecnica"].tolist() == ["P-I-B"]                 # esclusa dai calcoli
    with pytest.raises(ErroreModifica, match="ripristinarla"):
        t.modifica(k, "Descrizione", "x")

    m = t.aggiungi({"Sede tecnica": "p-i-a", "Descrizione": "Nuova"})    # codice libero: A è rimossa
    assert t.vista()[0].iloc[-1]["Origine"] == "MANUALE"
    with pytest.raises(ErroreModifica, match="già presente"):
        t.ripristina(k)                                                    # ora il codice è occupato
    t.rimuovi(m)                                                           # manuale: cancellata davvero
    assert len(t.vista()[0]) == 2
    t.ripristina(k)
    assert t.conta_modifiche() == 0


def test_note():
    t = nuova()
    k = chiave(t, "P-I-B")
    t.imposta_nota(k, "  verificare con l'ingegneria ")
    assert t.vista()[0].loc[1, "Note"] == "verificare con l'ingegneria"
    t.imposta_nota(k, "")
    assert t.note == {}


def test_nuova_base_conserva_o_scarta():
    t = nuova()
    t.modifica(chiave(t, "P-I-A"), "Descrizione", "Uno bis")
    t.rimuovi(chiave(t, "P-I-B"))
    t.aggiungi({"Sede tecnica": "P-I-M", "Descrizione": "Manuale"})

    t.imposta_base(df(("P-I-A", "Uno"), ("P-I-C", "Tre")), conserva_modifiche=True)
    assert t.dati().values.tolist() == [["P-I-A", "Uno bis"], ["P-I-C", "Tre"], ["P-I-M", "Manuale"]]
    assert t.orfane() == ["B\x1fP-I-B"]                                    # rimozione di una riga sparita
    t.elimina_orfane()
    assert t.orfane() == []

    t.imposta_base(df(("P-I-A", "Uno")), conserva_modifiche=False)
    assert t.dati().values.tolist() == [["P-I-A", "Uno"]] and t.conta_modifiche() == 0


def test_notifica_e_versione():
    chiamate = []
    t = Tabella(COLONNE, notifica=lambda: chiamate.append(1))
    t.imposta_base(df(("P-I-A", "Uno")))
    t.aggiungi({"Sede tecnica": "P-I-B"})
    assert len(chiamate) == 2 and t.versione == 2


def test_serializzazione():
    t = nuova()
    t.modifica(chiave(t, "P-I-A"), "Descrizione", "Uno bis")
    t.rimuovi(chiave(t, "P-I-B"))
    t.aggiungi({"Sede tecnica": "P-I-M", "Descrizione": "Manuale"})
    t.imposta_nota(chiave(t, "P-I-M"), "nota")
    copia = Tabella(COLONNE, normalizza={"Sede tecnica": normalizza_sede})
    copia.ripristina_da(t.serializza())
    assert copia.vista()[0].equals(t.vista()[0])
    assert copia.aggiungi({"Sede tecnica": "P-I-N"}) != chiave(t, "P-I-M")   # contatore ripristinato


def test_chiave_composta():
    t = Tabella(("Work Order", "Notification", "Sede tecnica"), chiave=("Work Order", "Notification"))
    t.imposta_base(pd.DataFrame({"Work Order": ["1", ""], "Notification": ["", "1"],
                                 "Sede tecnica": ["A", "B"]}))
    assert len(t.dati()) == 2                                  # stesso numero, tipo diverso
    t.aggiungi({"Notification": "2", "Sede tecnica": "C"})     # basta una delle colonne chiave
    with pytest.raises(ErroreModifica, match="Work Order o Notification"):
        t.aggiungi({"Sede tecnica": "D"})
    with pytest.raises(ErroreModifica, match="già presente"):
        t.aggiungi({"Work Order": "1", "Sede tecnica": "E"})
