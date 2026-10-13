import pandas as pd
import pytest

from conversione_sedi.check_parent import (
    COL_CHECK, COL_ORIGINE, COL_SEDE, parent, riepilogo, stato_finale, verifica_gerarchia,
)
from conversione_sedi.nucleo import carica_configurazione
from conversione_sedi.riconciliazione import Decisione, riconcilia


def tabella(*sedi):
    return pd.DataFrame({"Sede tecnica": list(sedi), "Descrizione": [f"D {s}" for s in sedi]})


def check(*sedi):
    out = verifica_gerarchia(pd.DataFrame({COL_SEDE: list(sedi)}))
    return dict(zip(out[COL_SEDE], out[COL_CHECK]))


@pytest.fixture
def conf(tmp_path):
    regole = tmp_path / "r.csv"
    regole.write_text("Regola_In;Codice_Out\nP-I-A-1;P-I-B-1\nP-I-X;P-I-Y\n", encoding="utf-8")
    trasf = tmp_path / "t.csv"
    trasf.write_text("Segmento;Valore_Atteso;Espressione\n99;*;X\n", encoding="utf-8")
    return carica_configurazione(regole, trasf)


# ---------------------------------------------------------------------------
# verifica_gerarchia
# ---------------------------------------------------------------------------
def test_parent():
    assert parent("ITE-OT0B-1E-01-B1-BM") == "ITE-OT0B-1E-01-B1"
    assert parent("ITE") == ""


def test_gerarchia_completa():
    esiti = check("USE-USS5", "USE-USS5-1E", "USE-USS5-1E-01", "USE-USS5-1E-01-C1")
    assert set(esiti.values()) == {"OK"}                   # la radice USE esiste sempre


def test_solo_parent_diretto():
    # manca USE-USS5-1E: segnalato solo sul figlio diretto, non sui livelli inferiori
    esiti = check("USE-USS5", "USE-USS5-1E-01", "USE-USS5-1E-01-C1")
    assert esiti["USE-USS5-1E-01"] == "Parent NOK (manca USE-USS5-1E)"
    assert esiti["USE-USS5-1E-01-C1"] == "OK"


def test_impianto_deve_esistere():
    assert check("USE-USS5-1E")["USE-USS5-1E"] == "Parent NOK (manca USE-USS5)"
    assert check("USE-USS5")["USE-USS5"] == "OK"
    assert check("USE")["USE"] == "OK"


def test_duplicati_e_piu_errori():
    out = verifica_gerarchia(pd.DataFrame({COL_SEDE: ["USE-USS5", "use-uss5-1e-01 ", "USE-USS5-1E-01"]}))
    assert out[COL_CHECK].tolist() == [
        "OK",
        "Valore duplicato | Parent NOK (manca USE-USS5-1E)",
        "Valore duplicato | Parent NOK (manca USE-USS5-1E)",
    ]
    assert riepilogo(out) == {"OK": 1, "Valore duplicato": 2, "Parent NOK": 2, "Sede vuota": 0}


def test_sede_vuota_e_colonne_conservate():
    df = pd.DataFrame({COL_SEDE: ["USE-USS5", "", None], "Altro": [1, 2, 3]})
    out = verifica_gerarchia(df)
    assert out[COL_CHECK].tolist() == ["OK", "Sede vuota", "Sede vuota"]
    assert out["Altro"].tolist() == [1, 2, 3] and COL_CHECK not in df.columns


def test_colonna_mancante():
    with pytest.raises(KeyError):
        verifica_gerarchia(pd.DataFrame({"Altro": ["X"]}))


# ---------------------------------------------------------------------------
# stato_finale
# ---------------------------------------------------------------------------
def test_stato_finale(conf):
    actual = tabella("P", "P-I", "P-I-A", "P-I-A-1", "P-I-OLD", "P-I-KEEP", "P-I-ZZ")
    new = tabella("P-I-A", "P-I-B", "P-I-B-1", "P-I-NEW")
    decisioni = {"P-I-OLD": Decisione.rimuovi(), "P-I-KEEP": Decisione.mantieni()}
    sf = stato_finale(riconcilia(actual, new, conf, decisioni))
    origini = dict(zip(sf[COL_SEDE], sf[COL_ORIGINE]))
    assert origini == {
        "P": "Esistente",                                  # livello 1 (esclusa)
        "P-I": "Esistente",                                # livello 2 (esclusa)
        "P-I-A": "Esistente",                              # invariata
        "P-I-B-1": "Modifica da P-I-A-1",
        "P-I-KEEP": "Mantenuta",
        "P-I-ZZ": "Provvisoria (Da decidere)",             # codice attuale finché non si decide
        "P-I-B": "Da creare",
        "P-I-NEW": "Da creare",
    }                                                      # P-I-OLD da rimuovere: assente
    assert sf[COL_SEDE].tolist() == sorted(sf[COL_SEDE])

    esiti = dict(zip(*verifica_gerarchia(sf)[[COL_SEDE, COL_CHECK]].T.values))
    assert set(esiti.values()) == {"OK"}


def test_stato_finale_parent_rimosso(conf):
    # P-I-A-1 diventa P-I-B-1, ma P-I-B non esiste in New né in SAP
    sf = stato_finale(riconcilia(tabella("P-I", "P-I-A", "P-I-A-1"), tabella("P-I-A", "P-I-B-1"), conf))
    esiti = dict(zip(*verifica_gerarchia(sf)[[COL_SEDE, COL_CHECK]].T.values))
    assert esiti["P-I-B-1"] == "Parent NOK (manca P-I-B)"


def test_stato_finale_conflitto_provvisorio(conf):
    # X in New ma la conversione darebbe Y, anch'essa in New: X resta provvisoria, Y non entra
    sf = stato_finale(riconcilia(tabella("P-I", "P-I-X"), tabella("P-I-X", "P-I-Y"), conf))
    origini = dict(zip(sf[COL_SEDE], sf[COL_ORIGINE]))
    assert origini == {"P-I": "Esistente", "P-I-X": "Provvisoria (Conflitto)"}
