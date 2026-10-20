import pandas as pd
import pytest

from conversione_sedi.nucleo import carica_configurazione
from conversione_sedi.piano_sap import (
    ErroreCestino, Riga, TipoStep as T, codice_cestino, costruisci_piano, firma_riconciliazione,
    radice_cestino,
)
from conversione_sedi.riconciliazione import Decisione, riconcilia


def tabella(*righe):
    dati = [(r, f"D {r}") if isinstance(r, str) else r for r in righe]
    return pd.DataFrame(dati, columns=["Sede tecnica", "Descrizione"])


@pytest.fixture
def conf_da(tmp_path):
    """Regole letterali {codice attuale: codice convertito}."""
    def crea(mappa):
        mappa = {"NESSUNA-SEDE-REALE": "X", **mappa}
        r = tmp_path / "r.csv"
        r.write_text("Regola_In;Codice_Out\n" + "".join(f"{a};{b}\n" for a, b in mappa.items()), encoding="utf-8")
        t = tmp_path / "t.csv"
        t.write_text("Segmento;Valore_Atteso;Espressione\n99;*;X\n", encoding="utf-8")
        return carica_configurazione(r, t)
    return crea


def piano_da(conf, actual, new, decisioni=None):
    return costruisci_piano(riconcilia(tabella(*actual), tabella(*new), conf, decisioni))


def schema(piano):
    """[(numero, tipo, [(sede, nuovo_codice, superiore)])]"""
    return [(s.numero, s.tipo, [(r.sede, r.nuovo_codice, r.superiore) for r in s.righe]) for s in piano.step]


P = "USE-P1"


# ---------------------------------------------------------------------------
# Codici
# ---------------------------------------------------------------------------
def test_codice_cestino():
    assert codice_cestino("USE-US64-1E-02-B4") == "USA-US64-1E-02-B4"
    assert codice_cestino("USE") == "USA"
    assert radice_cestino("USE-US64-1E-02-B4") == "USA"
    with pytest.raises(ErroreCestino, match="già \"A\""):
        codice_cestino("USA-US64-1E")
    with pytest.raises(ErroreCestino, match="meno di tre"):
        codice_cestino("US-X")


# ---------------------------------------------------------------------------
# Piani
# ---------------------------------------------------------------------------
def test_propagazione_creazione_e_rimozione(conf_da):
    # TR-T1 -> 01-T1 sotto 01 (da creare): FA segue per propagazione; TR va nel cestino dopo
    conf = conf_da({f"{P}-TR-T1": f"{P}-01-T1", f"{P}-TR-T1-FA": f"{P}-01-T1-FA"})
    piano = piano_da(conf,
                     [P, f"{P}-TR", f"{P}-TR-T1", f"{P}-TR-T1-FA"],
                     [P, (f"{P}-01", "Linea 01"), f"{P}-01-T1", f"{P}-01-T1-FA"],
                     {f"{P}-TR": Decisione.rimuovi()})
    assert piano.valido, piano.errori
    assert schema(piano) == [
        (1, T.CREAZIONE, [(f"{P}-01", f"{P}-01", P)]),
        (2, T.MODIFICA, [(f"{P}-TR-T1", f"{P}-01-T1", f"{P}-01")]),
        (3, T.RIMOZIONE, [(f"{P}-TR", f"USA-P1-TR", "USA")]),
    ]
    assert piano.step[1].propagate == [(f"{P}-TR-T1-FA", f"{P}-01-T1-FA")]
    assert piano.step[0].righe[0].descrizione == "Linea 01"
    assert piano.step[1].righe[0].descrizione == f"D {P}-01-T1"          # descrizione di New


def test_transcodifica_nello_stesso_file(conf_da):
    # B1 -> C1 trascina B1-BM in C1-BM, che va poi in C1-R1: la riga usa il codice transcodificato
    conf = conf_da({f"{P}-1E-B1": f"{P}-1E-C1", f"{P}-1E-B1-BM": f"{P}-1E-C1-R1"})
    piano = piano_da(conf, [P, f"{P}-1E", f"{P}-1E-B1", f"{P}-1E-B1-BM"],
                     [P, f"{P}-1E", f"{P}-1E-C1", f"{P}-1E-C1-R1"])
    assert schema(piano) == [(1, T.MODIFICA, [
        (f"{P}-1E-B1", f"{P}-1E-C1", f"{P}-1E"),
        (f"{P}-1E-C1-BM", f"{P}-1E-C1-R1", f"{P}-1E-C1"),
    ])]
    assert piano.step[0].righe[1].originale == f"{P}-1E-B1-BM"


def test_figlio_spostato_prima_della_rimozione_del_padre(conf_da):
    conf = conf_da({f"{P}-X-A": f"{P}-Y-A"})
    piano = piano_da(conf, [P, f"{P}-X", f"{P}-X-A", f"{P}-X-B", f"{P}-Y"],
                     [P, f"{P}-Y", f"{P}-Y-A"],
                     {f"{P}-X": Decisione.rimuovi(), f"{P}-X-B": Decisione.rimuovi()})
    assert schema(piano) == [
        (1, T.MODIFICA, [(f"{P}-X-A", f"{P}-Y-A", f"{P}-Y")]),
        (2, T.RIMOZIONE, [(f"{P}-X", "USA-P1-X", "USA")]),          # X-B la segue: nessuna riga
    ]
    assert piano.step[1].propagate == [(f"{P}-X-B", "USA-P1-X-B")]
    assert piano.step[1].righe[0].descrizione == f"D {P}-X"          # descrizione attuale


def test_creazione_in_fase_2(conf_da):
    conf = conf_da({f"{P}-B1": f"{P}-C1"})
    piano = piano_da(conf, [P, f"{P}-B1"], [P, f"{P}-C1", f"{P}-C1-NEW", f"{P}-C1-NEW-X"])
    assert schema(piano) == [
        (1, T.MODIFICA, [(f"{P}-B1", f"{P}-C1", P)]),
        (2, T.CREAZIONE, [(f"{P}-C1-NEW", f"{P}-C1-NEW", f"{P}-C1"),        # padre e figlio nello
                          (f"{P}-C1-NEW-X", f"{P}-C1-NEW-X", f"{P}-C1-NEW")]),  # stesso file, in ordine
    ]


def test_catena_libera_il_codice(conf_da):
    # A -> B mentre B -> C: B viene rinominata prima, nello stesso file
    conf = conf_da({f"{P}-A": f"{P}-B"})
    piano = piano_da(conf, [P, f"{P}-A", f"{P}-B"], [P, f"{P}-B", f"{P}-C"],
                     {f"{P}-B": Decisione.nuovo_codice(f"{P}-C")})
    assert schema(piano) == [(1, T.MODIFICA, [(f"{P}-B", f"{P}-C", P), (f"{P}-A", f"{P}-B", P)])]


def test_descrizioni_ultimo_step_e_avviso_lunghezza(conf_da):
    lunga = "x" * 41
    conf = conf_da({f"{P}-B1": f"{P}-C1"})
    piano = piano_da(conf, [P, (f"{P}-Z", "vecchia"), f"{P}-B1"], [P, (f"{P}-Z", lunga), f"{P}-C1"])
    assert [s.tipo for s in piano.step] == [T.MODIFICA, T.DESCRIZIONE]
    assert piano.step[1].righe == [Riga(f"{P}-Z", "", lunga, "", f"{P}-Z")]
    assert piano.avvisi and "40 caratteri" in piano.avvisi[0] and f"{P}-Z" in piano.avvisi[0]


def test_nessuna_operazione(conf_da):
    piano = piano_da(conf_da({}), [P, f"{P}-A"], [P, f"{P}-A"])
    assert piano.valido and piano.step == []


# ---------------------------------------------------------------------------
# Errori
# ---------------------------------------------------------------------------
def test_sede_trascinata_dalla_modifica(conf_da):
    conf = conf_da({f"{P}-B1": f"{P}-C1"})
    piano = piano_da(conf, [P, f"{P}-B1", f"{P}-B1-XX"], [P, f"{P}-C1", f"{P}-B1-XX"])
    assert not piano.valido and piano.step == []
    assert piano.errori == [f"{P}-B1-XX (Invariata) verrebbe trascinata dalla modifica di {P}-B1: "
                            "assegnarle un nuovo codice o rimuoverla."]


def test_sede_trascinata_dalla_rimozione(conf_da):
    piano = piano_da(conf_da({}), [P, f"{P}-X", f"{P}-X-K"], [P],
                     {f"{P}-X": Decisione.rimuovi(), f"{P}-X-K": Decisione.mantieni()})
    assert "verrebbe trascinata dalla rimozione" in piano.errori[0]


def test_primo_livello_gia_nel_cestino(conf_da):
    piano = piano_da(conf_da({}), ["USA-P1", "USA-P1-X"], ["USA-P1"], {"USA-P1-X": Decisione.rimuovi()})
    assert "già \"A\"" in piano.errori[0]


def test_piano_bloccato_dipendenza_impossibile(conf_da):
    # X va nel cestino ma New chiede X-1 sotto X: la creazione non potrà mai avvenire
    piano = piano_da(conf_da({}), [P, f"{P}-X"], [P, f"{P}-X-1"], {f"{P}-X": Decisione.rimuovi()})
    assert not piano.valido and piano.step == []
    assert piano.errori == [f"Creazione di {P}-X-1 bloccata: manca il padre {P}-X."]


def test_riconciliazione_incompleta(conf_da):
    piano = piano_da(conf_da({}), [P, f"{P}-A"], [P])                      # A: Da decidere
    assert piano.errori == ["Riconciliazione incompleta: 1 righe da risolvere in Check Actual."]


def test_firma(conf_da):
    conf = conf_da({})
    actual, new = tabella(P, f"{P}-A"), tabella(P)
    f1 = firma_riconciliazione(riconcilia(actual, new, conf, {f"{P}-A": Decisione.rimuovi()}))
    f2 = firma_riconciliazione(riconcilia(actual, new, conf, {f"{P}-A": Decisione.rimuovi()}))
    f3 = firma_riconciliazione(riconcilia(actual, new, conf, {f"{P}-A": Decisione.mantieni()}))
    assert f1 == f2 != f3
