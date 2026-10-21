"""Step SAP script nel modello del progetto: blocchi, piano, esecuzione."""
import pandas as pd
import pytest

pytest.importorskip("xlwt")

from conftest import REGOLE_TEST, TRASFORMAZIONI_TEST                     # noqa: E402
from conversione_sedi.nuova_codifica import valida_new                    # noqa: E402
from conversione_sedi.piano_sap import TipoStep                           # noqa: E402
from conversione_sedi.progetto import (                                   # noqa: E402
    ErroreProgetto, Progetto, Scheda, StatoScheda as S, StatoStep,
)
from conversione_sedi.riconciliazione import Decisione                    # noqa: E402
from conversione_sedi.tabella import ErroreModifica                       # noqa: E402

NEW = [("ITE-OT0B", "Impianto"), ("ITE-OT0B-1E", "Area 1"), ("ITE-OT0B-1E-01", "Linea 1"),
       ("ITE-OT0B-1E-01-C1", "Cluster"), ("ITE-OT0B-1E-01-C1-R1", "Rack 1")]
ACTUAL = [("ITE-OT0B", "Impianto"), ("ITE-OT0B-1E", "Area 1"), ("ITE-OT0B-1E-01", "Linea 1"),
          ("ITE-OT0B-1E-01-B1", "Batteria"), ("ITE-OT0B-1E-01-B1-BM", "Modulo")]
COLONNE_NO_WO = ["Sede tecnica", "Work Order", "Notification", "Descrizione", "Stato"]
VUOTO = pd.DataFrame(columns=COLONNE_NO_WO)


def tabella(righe):
    return pd.DataFrame(righe, columns=["Sede tecnica", "Descrizione"])


@pytest.fixture(autouse=True)
def impostazioni(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))


@pytest.fixture
def progetto(tmp_path):
    p = Progetto(REGOLE_TEST, TRASFORMAZIONI_TEST)
    p.imposta_new(valida_new(tabella(NEW)))
    p.imposta_actual(tabella(ACTUAL))
    p.imposta_decisione("ITE-OT0B-1E-01-B1", Decisione.rimuovi())
    return p


def pronto(p, tmp_path):
    p.imposta_no_wo(VUOTO, VUOTO, p.sedi_per_no_wo())
    p.salva(tmp_path / "ITE-OT0B.bessprj")
    return p


# ---------------------------------------------------------------------------
# Blocchi prima della generazione
# ---------------------------------------------------------------------------
def test_motivi_di_blocco(progetto, tmp_path):
    p = progetto
    assert p.stato(Scheda.SAP_SCRIPT) == S.BLOCCATA
    assert "No_Wo" in p.motivo_blocco(Scheda.SAP_SCRIPT)

    ordini = pd.DataFrame([{"Sede tecnica": "ITE-OT0B-1E-01-B1", "Work Order": "4711",
                            "Descrizione": "Ispezione", "Stato": "APER"}])
    p.imposta_no_wo(ordini, VUOTO.drop(columns=["Work Order"]).assign(Notification=[]), p.sedi_per_no_wo())
    assert "1 Work Order / Notification aperti" in p.motivo_blocco(Scheda.SAP_SCRIPT)
    vista, meta = p.no_wo.vista()
    p.no_wo.rimuovi(meta[0].chiave)                       # togliere la riga a mano non basta (D4)
    assert "aperti" in p.motivo_blocco(Scheda.SAP_SCRIPT)

    p.imposta_no_wo(VUOTO, VUOTO, p.sedi_per_no_wo())
    assert "salvare il progetto" in p.motivo_blocco(Scheda.SAP_SCRIPT)
    p.salva(tmp_path / "x.bessprj")
    assert p.motivo_blocco(Scheda.SAP_SCRIPT) is None and p.stato(Scheda.SAP_SCRIPT) == S.DA_ESEGUIRE
    with pytest.raises(ErroreProgetto, match="Nessun piano"):
        p.segna_caricato(1)


def test_riconciliazione_incompleta_blocca(progetto):
    progetto.imposta_decisione("ITE-OT0B-1E-01-B1", None)   # torna "Da decidere"
    assert "riconciliazione" in progetto.motivo_blocco(Scheda.SAP_SCRIPT)


# ---------------------------------------------------------------------------
# Generazione ed esecuzione
# ---------------------------------------------------------------------------
def test_genera_piano(progetto, tmp_path):
    p = pronto(progetto, tmp_path)
    piano = p.genera_piano()
    assert piano.valido
    assert [(s.numero, s.tipo) for s in piano.step] == [
        (1, TipoStep.CREAZIONE), (2, TipoStep.MODIFICA), (3, TipoStep.RIMOZIONE)]
    assert piano.step[2].righe[0].nuovo_codice == "ITA-OT0B-1E-01-B1"           # cestino ITA
    cartella = tmp_path / "SAP_ITE-OT0B"
    assert sorted(f.name for f in cartella.iterdir()) == [
        "FL_da_creare_Step_1.xlsx", "ZPM4R_FL_DES_MA_LOAD_modificare_upload_Step_2.xls", "ZPM4R_FL_DES_MA_LOAD_rimuovere_upload_Step_3.xls"]
    assert p.file_step(1) == cartella / "FL_da_creare_Step_1.xlsx"
    assert p.file_step(2) == cartella / "ZPM4R_FL_DES_MA_LOAD_modificare_upload_Step_2.xls"
    assert p.stato(Scheda.SAP_SCRIPT) == S.AGGIORNATA
    assert p.stati_step == [StatoStep.DA_CARICARE] * 3 and p.step_corrente() == 1


def test_dati_cambiati_dopo_la_generazione(progetto, tmp_path):
    p = pronto(progetto, tmp_path)
    p.genera_piano()
    vista, meta = p.new.vista()
    p.new.modifica(meta[2].chiave, "Descrizione", "Linea 1 nuova")              # prima dell'avvio: ammesso
    assert p.stato(Scheda.SAP_SCRIPT) == S.DA_AGGIORNARE
    with pytest.raises(ErroreProgetto, match="rigenerarli"):
        p.segna_caricato(1)
    piano = p.genera_piano()
    assert piano.step[-1].tipo == TipoStep.DESCRIZIONE
    assert p.stato(Scheda.SAP_SCRIPT) == S.AGGIORNATA


def test_esecuzione_in_ordine_e_blocco_dati(progetto, tmp_path):
    p = pronto(progetto, tmp_path)
    p.genera_piano()
    with pytest.raises(ErroreProgetto, match="solo sullo step 1"):
        p.segna_caricato(2)
    with pytest.raises(ErroreProgetto, match="non ammessa"):
        p.registra_esito(1, True)                                                  # non ancora caricato

    p.segna_caricato(1)
    assert p.piano_in_esecuzione and p.stati_step[0] == StatoStep.CARICATO
    # dati bloccati (D10), ma la verifica Check resta possibile
    with pytest.raises(ErroreProgetto, match="Interrompi piano"):
        p.imposta_decisione("ITE-OT0B-1E-01-B1", Decisione.mantieni())
    with pytest.raises(ErroreModifica, match="Interrompi piano"):
        p.new.aggiungi({"Sede tecnica": "ITE-OT0B-1E-09", "Descrizione": "x"})
    with pytest.raises(ErroreProgetto, match="Interrompi piano"):
        p.imposta_actual(tabella(ACTUAL))
    p.imposta_check_sap(tabella(NEW))

    p.registra_esito(1, False)                                                     # errori: si ricarica
    assert p.stati_step[0] == StatoStep.CON_ERRORI and p.step_corrente() == 1
    p.segna_caricato(1)
    p.registra_esito(1, True)
    assert p.step_corrente() == 2
    for n in (2, 3):
        p.segna_caricato(n)
        p.registra_esito(n, True)
    assert p.step_corrente() is None
    assert p.stato(Scheda.SAP_SCRIPT) == S.AGGIORNATA                              # resta utilizzabile

    p.interrompi_piano()
    assert not p.piano_in_esecuzione and p.piano is None
    p.imposta_decisione("ITE-OT0B-1E-01-B1", Decisione.mantieni())               # di nuovo modificabile


def test_piano_con_errori_non_scrive_file(progetto, tmp_path):
    p = progetto
    # B1-BM resta invariata a mano sotto B1 da rimuovere: verrebbe trascinata (D9)
    p.imposta_decisione("ITE-OT0B-1E-01-B1-BM", Decisione.mantieni())
    pronto(p, tmp_path)
    piano = p.genera_piano()
    assert not piano.valido and "trascinata" in piano.errori[0]
    assert p.piano is None and not (tmp_path / "SAP_ITE-OT0B").exists()


def test_salva_e_riapri_piano(progetto, tmp_path):
    p = pronto(progetto, tmp_path)
    p.genera_piano()
    p.segna_caricato(1)
    q = Progetto.apri(p.percorso)
    assert [s.tipo for s in q.piano.step] == [s.tipo for s in p.piano.step]
    assert q.piano.step[1].righe == p.piano.step[1].righe
    assert q.stati_step == p.stati_step and q.piano_in_esecuzione
    assert q.piano_cartella == tmp_path / "SAP_ITE-OT0B"
    assert q.stato(Scheda.SAP_SCRIPT) == S.AGGIORNATA                              # firma ricalcolata uguale
