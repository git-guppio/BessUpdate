from datetime import datetime

import pandas as pd
import pytest

from conversione_sedi.nuova_codifica import valida_new
from conversione_sedi.progetto import (
    ErroreProgetto, ImpiantoDiverso, Progetto, Scheda, StatoScheda as S, ultimo_progetto,
)
from conversione_sedi.riconciliazione import Decisione
from conversione_sedi.tabella import ErroreModifica
from conftest import REGOLE_TEST, TRASFORMAZIONI_TEST

NEW = [("ITE-OT0B", "Impianto"), ("ITE-OT0B-1E", "Area 1"), ("ITE-OT0B-1E-01", "Linea 1"),
       ("ITE-OT0B-1E-01-C1", "Cluster"), ("ITE-OT0B-1E-01-C1-R1", "Rack 1")]
ACTUAL = [("ITE-OT0B", "Impianto"), ("ITE-OT0B-1E", "Area 1"), ("ITE-OT0B-1E-01", "Linea 1"),
          ("ITE-OT0B-1E-01-B1", "Batteria"), ("ITE-OT0B-1E-01-B1-BM", "Modulo")]


def tabella(righe):
    return pd.DataFrame(righe, columns=["Sede tecnica", "Descrizione"])


def nc(righe=NEW):
    return valida_new(tabella(righe))


@pytest.fixture(autouse=True)
def impostazioni_temporanee(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))


@pytest.fixture
def progetto():
    p = Progetto(REGOLE_TEST, TRASFORMAZIONI_TEST)
    p.imposta_new(nc())
    p.imposta_actual(tabella(ACTUAL), quando=datetime(2026, 10, 13, 9, 0))
    return p


def ops(p):
    ric = p.riconciliazione()
    return dict(zip(ric.actual["Sede tecnica"], ric.actual["Operazione"]))


# ---------------------------------------------------------------------------
# Stati delle schede
# ---------------------------------------------------------------------------
def test_stati_progetto_vuoto():
    p = Progetto(REGOLE_TEST, TRASFORMAZIONI_TEST)
    assert p.stato(Scheda.NEW) == S.DA_ESEGUIRE
    for scheda in (Scheda.ACTUAL, Scheda.FL_DA_CREARE, Scheda.CHECK_PARENT, Scheda.NO_WO, Scheda.CHECK):
        assert p.stato(scheda) == S.BLOCCATA
    assert p.riconciliazione() is None and p.fl_da_creare() is None and p.verifica() is None


def test_stati_dopo_new():
    p = Progetto(REGOLE_TEST, TRASFORMAZIONI_TEST)
    p.imposta_new(nc())
    assert p.impianto == "ITE-OT0B"
    assert p.stato(Scheda.ACTUAL) == S.DA_ESEGUIRE
    assert p.stato(Scheda.CHECK) == S.DA_ESEGUIRE
    assert p.stato(Scheda.CHECK_ACTUAL) == S.BLOCCATA


def test_flusso_completo(progetto):
    p = progetto
    assert p.stato(Scheda.CHECK_ACTUAL) == S.AGGIORNATA
    fl = p.fl_da_creare()
    assert list(fl.columns) == ["Sede tecnica", "Descrizione", "Codice_Out", "Nuove sedi tecniche", "Esito"]
    assert ops(p)["ITE-OT0B-1E-01-B1-BM"] == "Modifica"
    assert ops(p)["ITE-OT0B-1E-01-B1"] == "Da decidere"
    assert p.stato(Scheda.NO_WO) == S.BLOCCATA                      # riconciliazione incompleta

    p.imposta_decisione("ite-ot0b-1e-01-b1", Decisione.rimuovi())
    assert p.riconciliazione().completa
    # solo le sedi da rimuovere: le modificate mantengono l'ID interno SAP (D2)
    assert p.sedi_per_no_wo() == ["ITE-OT0B-1E-01-B1"]
    assert p.stato(Scheda.NO_WO) == S.DA_ESEGUIRE

    vuoto = pd.DataFrame(columns=["Sede tecnica", "Work Order", "Notification", "Descrizione", "Stato"])
    p.imposta_no_wo(vuoto, vuoto, ["ITE-OT0B-1E-01-ALTRA"])         # estrazione su un altro insieme
    assert p.stato(Scheda.NO_WO) == S.DA_AGGIORNARE
    p.imposta_no_wo(vuoto, vuoto, p.sedi_per_no_wo())
    assert p.stato(Scheda.NO_WO) == S.AGGIORNATA

    p.imposta_decisione("ITE-OT0B-1E-01-B1", Decisione.mantieni())  # nessuna sede da rimuovere
    assert p.sedi_per_no_wo() == [] and p.stato(Scheda.NO_WO) == S.AGGIORNATA


def test_ricalcolo_automatico_dopo_modifica_manuale(progetto):
    p = progetto
    assert ops(p)["ITE-OT0B-1E-01"] == "Invariata"
    vista, meta = p.new.vista()
    riga = vista.index[vista["Sede tecnica"] == "ITE-OT0B-1E-01"][0]
    p.new.modifica(meta[riga].chiave, "Descrizione", "Linea 1 nuova")
    assert ops(p)["ITE-OT0B-1E-01"] == "Modifica descrizione"


def test_cache(progetto):
    assert progetto.riconciliazione() is progetto.riconciliazione()


def test_check_parent(progetto):
    p = progetto
    p.imposta_decisione("ITE-OT0B-1E-01-B1", Decisione.rimuovi())
    vista, meta = p.check_parent_vista()
    esiti = dict(zip(vista["Nuove sedi tecniche"], vista["Check"]))
    assert esiti == {"ITE-OT0B": "OK", "ITE-OT0B-1E": "OK", "ITE-OT0B-1E-01": "OK",
                     "ITE-OT0B-1E-01-C1": "OK", "ITE-OT0B-1E-01-C1-R1": "OK"}

    # rimozione manuale di una riga: il figlio diventa Parent NOK; la riga resta, senza Check
    k = meta[list(vista["Nuove sedi tecniche"]).index("ITE-OT0B-1E-01-C1")].chiave
    p.check_parent.rimuovi(k)
    vista, _ = p.check_parent_vista()
    esiti = dict(zip(vista["Nuove sedi tecniche"], vista["Check"]))
    assert esiti["ITE-OT0B-1E-01-C1-R1"] == "Parent NOK (manca ITE-OT0B-1E-01-C1)"
    assert esiti["ITE-OT0B-1E-01-C1"] == ""

    # la modifica manuale sopravvive al ricalcolo dello stato finale
    p.imposta_decisione("ITE-OT0B-1E-01-B1", Decisione.mantieni())
    vista, meta = p.check_parent_vista()
    riga = list(vista["Nuove sedi tecniche"]).index("ITE-OT0B-1E-01-C1")
    assert meta[riga].rimossa


def test_check_parent_validazione_impianto(progetto):
    progetto.check_parent_vista()
    with pytest.raises(ErroreModifica, match="non appartiene all'impianto ITE-OT0B"):
        progetto.check_parent.aggiungi({"Nuove sedi tecniche": "ITE-XX-1E"})


def test_verifica(progetto):
    p = progetto
    p.imposta_check_sap(tabella(NEW[:4] + [("ITE-OT0B-OLD", "Vecchia")]))
    assert p.stato(Scheda.CHECK) == S.AGGIORNATA
    v = p.verifica()
    assert v.conteggi()["Mancante in SAP"] == 1 and v.conteggi()["In eccesso in SAP"] == 1


def test_risolvi_conflitto(tmp_path):
    p = Progetto(REGOLE_TEST, TRASFORMAZIONI_TEST)
    p.imposta_new(nc([("ITE-OT0B-1E-01-C1-R1", "Rack")]))
    # due Sedi verso lo stesso codice: B1-BM e B1-BM convertita a mano
    p.imposta_actual(tabella([("ITE-OT0B-1E-01-B1-BM", "A"), ("ITE-OT0B-1E-01-B9", "B")]))
    p.imposta_decisione("ITE-OT0B-1E-01-B9", Decisione.nuovo_codice("ITE-OT0B-1E-01-C1-R1"))
    assert set(ops(p).values()) == {"Conflitto"}
    p.risolvi_conflitto("ITE-OT0B-1E-01-B1-BM", ["ITE-OT0B-1E-01-B1-BM", "ITE-OT0B-1E-01-B9"])
    assert ops(p) == {"ITE-OT0B-1E-01-B1-BM": "Modifica", "ITE-OT0B-1E-01-B9": "Da rimuovere"}


# ---------------------------------------------------------------------------
# Impianto e nuove importazioni
# ---------------------------------------------------------------------------
def test_actual_di_altro_impianto(progetto):
    with pytest.raises(ErroreProgetto, match="impianto diverso da ITE-OT0B: ITE-XX-1E"):
        progetto.imposta_actual(tabella([("ITE-XX-1E", "x")]))


def test_actual_senza_new():
    with pytest.raises(ErroreProgetto, match="Caricare prima"):
        Progetto(REGOLE_TEST, TRASFORMAZIONI_TEST).imposta_actual(tabella(ACTUAL))


def test_new_di_altro_impianto(progetto):
    altro = nc([("USE-USS5-1E", "A")])
    with pytest.raises(ImpiantoDiverso) as e:
        progetto.imposta_new(altro)
    assert (e.value.attuale, e.value.nuovo) == ("ITE-OT0B", "USE-USS5")
    progetto.imposta_new(altro, azzera=True)
    assert progetto.impianto == "USE-USS5" and progetto.actual.vuota
    assert progetto.stato(Scheda.ACTUAL) == S.DA_ESEGUIRE


def test_nuova_estrazione_conserva_o_scarta(progetto):
    p = progetto
    p.imposta_decisione("ITE-OT0B-1E-01-B1", Decisione.rimuovi())
    p.actual.aggiungi({"Sede tecnica": "ITE-OT0B-1E-02", "Descrizione": "Manuale"})
    assert p.conta_modifiche_manuali(Scheda.ACTUAL) == 2

    p.imposta_actual(tabella(ACTUAL), conserva_modifiche=True)
    assert p.conta_modifiche_manuali(Scheda.ACTUAL) == 2
    p.imposta_actual(tabella(ACTUAL), conserva_modifiche=False)
    assert p.conta_modifiche_manuali(Scheda.ACTUAL) == 0 and p.decisioni == {}


def test_modifica_manuale_new_altro_impianto(progetto):
    with pytest.raises(ErroreModifica, match="non appartiene"):
        progetto.new.aggiungi({"Sede tecnica": "USE-USS5-1E"})


# ---------------------------------------------------------------------------
# Salvataggio
# ---------------------------------------------------------------------------
def test_salva_e_apri(progetto, tmp_path):
    p = progetto
    p.imposta_decisione("ITE-OT0B-1E-01-B1", Decisione.nuovo_codice("ITE-OT0B-1E-01-C1"))
    p.new.aggiungi({"Sede tecnica": "ITE-OT0B-1E-02", "Descrizione": "Manuale"})
    file = p.salva(tmp_path / "ITE-OT0B")
    assert file.name == "ITE-OT0B.bessprj"
    assert ultimo_progetto() == file

    q = Progetto.apri(file)
    assert q.impianto == "ITE-OT0B"
    assert q.decisioni == p.decisioni
    assert q.estrazioni["actual"] == datetime(2026, 10, 13, 9, 0)
    assert q.new.vista()[0].equals(p.new.vista()[0])
    assert q.riconciliazione().actual.equals(p.riconciliazione().actual)


def test_salvataggio_automatico(progetto, tmp_path):
    p = progetto
    file = p.salva(tmp_path / "auto.bessprj")
    p.imposta_decisione("ITE-OT0B-1E-01-B1", Decisione.rimuovi())
    assert Progetto.apri(file).decisioni == {"ITE-OT0B-1E-01-B1": Decisione.rimuovi()}
    p.actual.aggiungi({"Sede tecnica": "ITE-OT0B-1E-09", "Descrizione": "x"})
    assert not Progetto.apri(file).actual.vuota
    assert len(Progetto.apri(file).actual.aggiunte) == 1


def test_check_parent_calcolato_non_salva(progetto, tmp_path, monkeypatch):
    file = progetto.salva(tmp_path / "x.bessprj")
    salvataggi = []
    monkeypatch.setattr(progetto, "salva", lambda *a, **k: salvataggi.append(1))
    progetto.check_parent_vista()                   # ricalcolo dello stato finale
    assert salvataggi == [] and file.is_file()


def test_apri_file_non_valido(tmp_path):
    f = tmp_path / "rotto.bessprj"
    f.write_text("non è un progetto", encoding="utf-8")
    with pytest.raises(ErroreProgetto, match="Impossibile aprire"):
        Progetto.apri(f)
