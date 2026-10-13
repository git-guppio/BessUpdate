import pandas as pd
import pytest

from conversione_sedi.ingresso_uscita import REGOLE_PREDEFINITE, TRASFORMAZIONI_PREDEFINITE
from conversione_sedi.nucleo import carica_configurazione
from conversione_sedi.riconciliazione import (
    Decisione, Operazione as Op, StatoNew as St, normalizza_descrizione, riconcilia,
)


def tabella(*righe):
    """Righe "SEDE" oppure ("SEDE", "Descrizione")."""
    dati = [(r, f"Descr {r}") if isinstance(r, str) else r for r in righe]
    return pd.DataFrame(dati, columns=["Sede tecnica", "Descrizione"])


@pytest.fixture
def conf_predefinita():
    return carica_configurazione(REGOLE_PREDEFINITE, TRASFORMAZIONI_PREDEFINITE)


@pytest.fixture
def conf_da(tmp_path):
    """Configurazione con regole letterali: {codice attuale: codice convertito}."""
    def crea(mappa):
        regole = tmp_path / "r.csv"
        mappa = {"NESSUNA-SEDE-REALE": "X", **mappa}       # almeno una regola valida
        regole.write_text("Regola_In;Codice_Out\n"
                          + "".join(f"{a};{b}\n" for a, b in mappa.items()), encoding="utf-8")
        trasf = tmp_path / "t.csv"
        trasf.write_text("Segmento;Valore_Atteso;Espressione\n99;*;X\n", encoding="utf-8")
        return carica_configurazione(regole, trasf)
    return crea


def op(ric, sede):
    return ric.actual.set_index("Sede tecnica").loc[sede, "Operazione"]


def stato(ric, sede):
    return ric.new.set_index("Sede tecnica").loc[sede, "Stato"]


def campo(ric, sede, colonna):
    return ric.actual.set_index("Sede tecnica").loc[sede, colonna]


# ---------------------------------------------------------------------------
# Scenario con le regole reali (config/)
# ---------------------------------------------------------------------------
def test_scenario_completo(conf_predefinita):
    actual = tabella("ITE", "ITE-OT0B",
                     ("ITE-OT0B-1E", "Area 1"),
                     ("ITE-OT0B-1E-01", "Linea  1 "),
                     ("ITE-OT0B-1E-01-B1-BM", "Modulo"),
                     "ITE-OT0B-1E-01-B1-BS",
                     "ITE-OT0B-1E-XX")
    new = tabella("ITE-OT0B",
                  ("ITE-OT0B-1E", "Area 1"),
                  ("ITE-OT0B-1E-01", "Linea 1 nuova"),
                  ("ITE-OT0B-1E-01-C1-R1", "Rack 1"),
                  "ITE-OT0B-1E-02")
    ric = riconcilia(actual, new, conf_predefinita)

    assert op(ric, "ITE") == Op.ESCLUSA
    assert op(ric, "ITE-OT0B") == Op.ESCLUSA
    assert op(ric, "ITE-OT0B-1E") == Op.INVARIATA
    assert op(ric, "ITE-OT0B-1E-01") == Op.MODIFICA_DESCRIZIONE
    assert op(ric, "ITE-OT0B-1E-01-B1-BM") == Op.MODIFICA
    assert campo(ric, "ITE-OT0B-1E-01-B1-BM", "Nuova sede tecnica") == "ITE-OT0B-1E-01-C1-R1"
    assert campo(ric, "ITE-OT0B-1E-01-B1-BM", "Nuova descrizione") == "Rack 1"
    assert campo(ric, "ITE-OT0B-1E-01-B1-BM", "Sequenza") == 1
    assert op(ric, "ITE-OT0B-1E-01-B1-BS") == Op.DA_VERIFICARE         # convertita, assente in New
    assert "ITE-OT0B-1E-01-C1-BS assente in New" in campo(ric, "ITE-OT0B-1E-01-B1-BS", "Motivo")
    assert op(ric, "ITE-OT0B-1E-XX") == Op.DA_DECIDERE                 # nessuna regola

    assert stato(ric, "ITE-OT0B") == St.ESCLUSA
    assert stato(ric, "ITE-OT0B-1E") == St.ESISTENTE
    assert stato(ric, "ITE-OT0B-1E-01") == St.ESISTENTE_DESCRIZIONE
    assert stato(ric, "ITE-OT0B-1E-01-C1-R1") == St.DA_MODIFICA
    assert ric.new.set_index("Sede tecnica").loc["ITE-OT0B-1E-01-C1-R1", "Sede di provenienza"] \
        == "ITE-OT0B-1E-01-B1-BM"
    assert stato(ric, "ITE-OT0B-1E-02") == St.DA_CREARE

    assert ric.righe_aperte == 2 and not ric.completa
    assert ric.riepilogo_actual()["Esclusa"] == 2


def test_risoluzione_manuale_completa(conf_predefinita):
    actual = tabella("ITE-OT0B-1E-01-B1-BS", "ITE-OT0B-1E-XX", "ITE-OT0B-1E-YY")
    new = tabella("ITE-OT0B-1E-ZZ")
    decisioni = {"ite-ot0b-1e-01-b1-bs": Decisione.rimuovi(),            # normalizzazione chiave
                 "ITE-OT0B-1E-XX": Decisione.mantieni(),
                 "ITE-OT0B-1E-YY": Decisione.nuovo_codice(" ite-ot0b-1e-zz ")}
    ric = riconcilia(actual, new, conf_predefinita, decisioni)
    assert op(ric, "ITE-OT0B-1E-01-B1-BS") == Op.DA_RIMUOVERE
    assert op(ric, "ITE-OT0B-1E-XX") == Op.MANTENUTA
    assert op(ric, "ITE-OT0B-1E-YY") == Op.MODIFICA
    assert campo(ric, "ITE-OT0B-1E-YY", "Decisione manuale") == "Sì"
    assert stato(ric, "ITE-OT0B-1E-ZZ") == St.DA_MODIFICA
    assert ric.completa


# ---------------------------------------------------------------------------
# Decisioni manuali non valide
# ---------------------------------------------------------------------------
def test_codice_manuale_assente_in_new(conf_da):
    ric = riconcilia(tabella("P-I-A"), tabella("P-I-B"), conf_da({}),
                     {"P-I-A": Decisione.nuovo_codice("P-I-C")})
    assert op(ric, "P-I-A") == Op.DA_VERIFICARE
    assert "P-I-C assente in New" in campo(ric, "P-I-A", "Motivo")


def test_rimozione_di_sede_presente_in_new(conf_da):
    ric = riconcilia(tabella("P-I-A"), tabella("P-I-A"), conf_da({}), {"P-I-A": Decisione.rimuovi()})
    assert op(ric, "P-I-A") == Op.DA_VERIFICARE
    assert stato(ric, "P-I-A") == St.IN_SOSPESO


def test_decisioni_orfane(conf_da):
    ric = riconcilia(tabella("P-I-A"), tabella("P-I-A"), conf_da({}),
                     {"P-I-SPARITA": Decisione.rimuovi()})
    assert any("orfane" in a and "P-I-SPARITA" in a for a in ric.avvisi)


# ---------------------------------------------------------------------------
# Conflitti
# ---------------------------------------------------------------------------
def test_conflitto_n_a_1_e_risoluzione(conf_da):
    conf = conf_da({"P-I-A": "P-I-T", "P-I-B": "P-I-T"})
    actual, new = tabella("P-I-A", "P-I-B"), tabella("P-I-T")
    ric = riconcilia(actual, new, conf)
    assert op(ric, "P-I-A") == op(ric, "P-I-B") == Op.CONFLITTO
    assert stato(ric, "P-I-T") == St.IN_SOSPESO
    assert not ric.completa

    ric = riconcilia(actual, new, conf, {"P-I-B": Decisione.rimuovi()})
    assert op(ric, "P-I-A") == Op.MODIFICA and op(ric, "P-I-B") == Op.DA_RIMUOVERE
    assert stato(ric, "P-I-T") == St.DA_MODIFICA and ric.completa


def test_codice_occupato_da_sede_invariata(conf_da):
    # X è già in New e resta; Z verrebbe convertita in X -> conflitto manuale
    conf = conf_da({"P-I-Z": "P-I-X"})
    actual, new = tabella("P-I-X", "P-I-Z"), tabella("P-I-X")
    ric = riconcilia(actual, new, conf)
    assert op(ric, "P-I-X") == op(ric, "P-I-Z") == Op.CONFLITTO

    ric = riconcilia(actual, new, conf, {"P-I-Z": Decisione.rimuovi()})
    assert op(ric, "P-I-X") == Op.INVARIATA and op(ric, "P-I-Z") == Op.DA_RIMUOVERE


def test_identita_contro_conversione(conf_da):
    # X è in New, ma le regole la porterebbero in Y, anch'essa in New
    conf = conf_da({"P-I-X": "P-I-Y"})
    actual, new = tabella("P-I-X"), tabella("P-I-X", "P-I-Y")
    ric = riconcilia(actual, new, conf)
    assert op(ric, "P-I-X") == Op.CONFLITTO
    assert stato(ric, "P-I-X") == stato(ric, "P-I-Y") == St.IN_SOSPESO

    ric = riconcilia(actual, new, conf, {"P-I-X": Decisione.mantieni()})
    assert op(ric, "P-I-X") == Op.INVARIATA
    assert stato(ric, "P-I-Y") == St.DA_CREARE


def test_identita_con_conversione_fuori_new(conf_da):
    # X è in New; la conversione darebbe Y assente in New: X resta invariata
    ric = riconcilia(tabella("P-I-X"), tabella("P-I-X"), conf_da({"P-I-X": "P-I-Y"}))
    assert op(ric, "P-I-X") == Op.INVARIATA


def test_codice_occupato_da_sede_da_rimuovere(conf_da):
    # il contrassegno di cancellazione non libera il codice
    conf = conf_da({"P-I-A": "P-I-T"})
    ric = riconcilia(tabella("P-I-A", "P-I-T"), tabella("P-I-T"), conf,
                     {"P-I-T": Decisione.rimuovi()})
    assert op(ric, "P-I-T") == Op.DA_VERIFICARE          # in New: rimozione non coerente
    assert op(ric, "P-I-A") == Op.CONFLITTO
    assert "occupato in SAP da P-I-T" in campo(ric, "P-I-A", "Motivo")


def test_catena_di_rinomine_ordinata(conf_da):
    # A -> B mentre B -> C: B va rinominata prima di A
    conf = conf_da({"P-I-A": "P-I-B"})
    ric = riconcilia(tabella("P-I-A", "P-I-B"), tabella("P-I-B", "P-I-C"), conf,
                     {"P-I-B": Decisione.nuovo_codice("P-I-C")})
    assert op(ric, "P-I-A") == op(ric, "P-I-B") == Op.MODIFICA
    assert campo(ric, "P-I-B", "Sequenza") < campo(ric, "P-I-A", "Sequenza")
    assert ric.new.set_index("Sede tecnica").loc["P-I-B", "Sede di provenienza"] == "P-I-A"
    assert ric.completa


def test_rinomina_circolare(conf_da):
    decisioni = {"P-I-A": Decisione.nuovo_codice("P-I-B"), "P-I-B": Decisione.nuovo_codice("P-I-A")}
    ric = riconcilia(tabella("P-I-A", "P-I-B"), tabella("P-I-A", "P-I-B"), conf_da({}), decisioni)
    assert op(ric, "P-I-A") == op(ric, "P-I-B") == Op.CONFLITTO
    assert "circolare: P-I-A -> P-I-B -> P-I-A" in campo(ric, "P-I-A", "Motivo")
    assert stato(ric, "P-I-A") == stato(ric, "P-I-B") == St.IN_SOSPESO


def test_conflitto_propagato_lungo_la_catena(conf_da):
    # A -> B, ma B (rinominata in C a mano) è in conflitto con D -> C: anche A va in conflitto
    conf = conf_da({"P-I-A": "P-I-B", "P-I-D": "P-I-C"})
    ric = riconcilia(tabella("P-I-A", "P-I-B", "P-I-D"), tabella("P-I-B", "P-I-C"), conf,
                     {"P-I-B": Decisione.nuovo_codice("P-I-C")})
    assert op(ric, "P-I-B") == op(ric, "P-I-D") == Op.CONFLITTO
    assert op(ric, "P-I-A") == Op.CONFLITTO
    assert "occupato in SAP da P-I-B" in campo(ric, "P-I-A", "Motivo")


def test_livelli_1_2_mai_toccati(conf_da):
    conf = conf_da({"P-I": "P-J"})
    ric = riconcilia(tabella("P", "P-I"), tabella("P-J"), conf, {"P": Decisione.rimuovi()})
    assert op(ric, "P") == op(ric, "P-I") == Op.ESCLUSA
    assert stato(ric, "P-J") == St.ESCLUSA
    assert ric.completa


# ---------------------------------------------------------------------------
# Descrizioni e input
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("attuale, nuova, atteso", [
    ("Rack 1", "Rack 1", Op.INVARIATA),
    ("  Rack   1 ", "Rack 1", Op.INVARIATA),                 # spazi ignorati
    ("rack 1", "Rack 1", Op.MODIFICA_DESCRIZIONE),           # maiuscole contano
    ('"Rack 1"', "Rack 1", Op.MODIFICA_DESCRIZIONE),         # virgolette contano
])
def test_confronto_descrizioni(conf_da, attuale, nuova, atteso):
    ric = riconcilia(tabella(("P-I-A", attuale)), tabella(("P-I-A", nuova)), conf_da({}))
    assert op(ric, "P-I-A") == atteso


def test_normalizza_descrizione():
    assert normalizza_descrizione("  a \t b  ") == "a b"
    assert normalizza_descrizione(None) == ""


def test_input_normalizzati_e_duplicati(conf_da):
    actual = tabella(" p-i-a ", "P-I-A", "", None)
    new = tabella("P-I-A", "p-i-a")
    ric = riconcilia(actual, new, conf_da({}))
    assert ric.actual["Sede tecnica"].tolist() == ["P-I-A"]
    assert len(ric.new) == 1
    assert any(a.startswith("Actual: Sedi tecniche duplicate") for a in ric.avvisi)
    assert any(a.startswith("New: Sedi tecniche duplicate") for a in ric.avvisi)


def test_colonna_mancante(conf_da):
    with pytest.raises(KeyError, match="Descrizione"):
        riconcilia(pd.DataFrame({"Sede tecnica": ["P-I-A"]}), tabella("P-I-A"), conf_da({}))
