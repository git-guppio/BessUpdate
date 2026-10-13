import pandas as pd
import pytest

from conversione_sedi.nucleo import (
    ESITO_DA_VERIFICARE, ESITO_NESSUNA_CORRISPONDENZA, ESITO_OK, ESITO_VUOTA,
    ErroreConfigurazione, carica_configurazione, converti, elabora_dataframe, riepilogo,
)

REGOLE_CSV = """Regola_In;Codice_Out
++E-++++-+E-TR-T1;++E-++++-+E-01-T1
++E-++++-+E-++-B+-BM;++E-++++-+E-++-C1-R+
++E-++++-+E-++-B1-BS;++E-++++-+E-++-C1-BS
++E-++++-+E-++-B1-BC;++E-++++-+E-++-C1-BC
++E-++++-+E-++-B1-CB;++E-++++-+E-++-C1-CB
++E-++++-0E;++E-++++-1A
++E-++++-0E-SA;++E-++++-1A-S1
++E-++++-0E-N0;++E-++++-1A-CS
++E-++++-+E-MV-I+-AT;++E-++++-+E-nn-MV-AT
++E-++++-+E-MV-I+-VT;++E-++++-+E-nn-MV-VT
++E-++++-+E-MV-I+;++E-++++-+E-nn-MV-RM
"""

TRASFORMAZIONI_CSV = """Segmento;Valore_Atteso;Espressione
1;*;{S1}
2;*;{S2}
3;+E;{S3}
4;++;{S4}
4;nn;0{S5.2}
6;R+;R{S5.2}
"""


def scrivi(tmp_path, nome, testo, encoding="utf-8"):
    p = tmp_path / nome
    p.write_text(testo, encoding=encoding)
    return p


@pytest.fixture
def conf(tmp_path):
    return carica_configurazione(scrivi(tmp_path, "regole.csv", REGOLE_CSV),
                                 scrivi(tmp_path, "trasformazioni.csv", TRASFORMAZIONI_CSV))


@pytest.mark.parametrize("sede, codice_out, attesa", [
    ("ITE-OT0B-1E-MV-I1-AT", "++E-++++-+E-nn-MV-AT", "ITE-OT0B-1E-01-MV-AT"),
    ("ITE-OT0B-1E-01-B1-BS", "++E-++++-+E-++-C1-BS", "ITE-OT0B-1E-01-C1-BS"),
    ("ITE-OT0B-1E-01-B1-BM", "++E-++++-+E-++-C1-R+", "ITE-OT0B-1E-01-C1-R1"),
    ("ITE-OT0B-1E-MV-I1",    "++E-++++-+E-nn-MV-RM", "ITE-OT0B-1E-01-MV-RM"),
    ("ITE-OT0B-1E-TR-T1",    "++E-++++-+E-01-T1",    "ITE-OT0B-1E-01-T1"),
    ("ITE-UD0B-0E",          "++E-++++-1A",          "ITE-UD0B-1A"),
    ("ITE-UD0B-0E-N0",       "++E-++++-1A-CS",       "ITE-UD0B-1A-CS"),
    ("  ite-ot0b-0e-sa ",    "++E-++++-1A-S1",       "ITE-OT0B-1A-S1"),
])
def test_esempi(conf, sede, codice_out, attesa):
    r = converti(sede, conf)
    assert (r.codice_out, r.nuova_sede_tecnica, r.esito) == (codice_out, attesa, ESITO_OK)


@pytest.mark.parametrize("sede", [
    "ITE-OT0B-00",          # nessuna regola compatibile
    "ITE-OT-B-1E",          # il jolly non accetta il separatore "-"
    "ITE-OT_B-1E",          # il jolly non accetta caratteri speciali
    "ITE-OT0B-1E-01-B1-BM-XX",  # lunghezza diversa
])
def test_nessuna_corrispondenza(conf, sede):
    assert converti(sede, conf).esito == ESITO_NESSUNA_CORRISPONDENZA


def test_vuota(conf):
    for v in ("", "   ", None, float("nan")):
        assert converti(v, conf).esito == ESITO_VUOTA


def test_priorita_regola_piu_specifica(tmp_path):
    regole = "Regola_In;Codice_Out\n+++-+;GENERICA\nAB+-+;SPECIFICA\nAB+-1;SPECIFICISSIMA\n"
    trasf = "Segmento;Valore_Atteso;Espressione\n9;*;X\n"
    conf = carica_configurazione(scrivi(tmp_path, "r.csv", regole), scrivi(tmp_path, "t.csv", trasf))
    assert converti("ABC-1", conf).codice_out == "SPECIFICISSIMA"
    assert converti("ABC-2", conf).codice_out == "SPECIFICA"
    assert converti("XYZ-2", conf).codice_out == "GENERICA"


def test_parita_jolly_vince_la_prima(tmp_path):
    regole = "Regola_In;Codice_Out\nA+;PRIMA\n+B;SECONDA\n"
    trasf = "Segmento;Valore_Atteso;Espressione\n9;*;X\n"
    conf = carica_configurazione(scrivi(tmp_path, "r.csv", regole), scrivi(tmp_path, "t.csv", trasf))
    assert converti("AB", conf).codice_out == "PRIMA"


def test_segnaposto_irrisolto(tmp_path):
    trasf = "Segmento;Valore_Atteso;Espressione\n1;*;{S1}\n2;*;{S2}\n3;+E;{S3}\n"  # manca la regola nn
    conf = carica_configurazione(scrivi(tmp_path, "r.csv", REGOLE_CSV), scrivi(tmp_path, "t.csv", trasf))
    r = converti("ITE-OT0B-1E-MV-I1", conf)
    assert r.esito == ESITO_DA_VERIFICARE
    assert r.nuova_sede_tecnica == "DA VERIFICARE: ITE-OT0B-1E-nn-MV-RM"


def test_riferimento_inesistente(tmp_path):
    regole = "Regola_In;Codice_Out\n++E-++++-0E;++E-++++-nn\n"
    trasf = "Segmento;Valore_Atteso;Espressione\n3;nn;0{S5.2}\n"   # la Sede ha solo 3 segmenti
    conf = carica_configurazione(scrivi(tmp_path, "r.csv", regole), scrivi(tmp_path, "t.csv", trasf))
    r = converti("ITE-OT0B-0E", conf)
    assert r.esito == ESITO_DA_VERIFICARE
    assert r.nuova_sede_tecnica == "DA VERIFICARE: ++E-++++-nn"


def test_valore_atteso_sensibile_alle_maiuscole(tmp_path):
    regole = "Regola_In;Codice_Out\nAB-+1;X-NN\nAB-+2;X-nn\n"
    trasf = "Segmento;Valore_Atteso;Espressione\n2;nn;00\n"
    conf = carica_configurazione(scrivi(tmp_path, "r.csv", regole), scrivi(tmp_path, "t.csv", trasf))
    assert converti("AB-C1", conf).nuova_sede_tecnica == "X-NN"   # NN è un valore letterale
    assert converti("AB-C2", conf).nuova_sede_tecnica == "X-00"   # nn è un segnaposto


def test_csv_virgola_cp1252_e_intestazioni_flessibili(tmp_path):
    regole = REGOLE_CSV.replace(";", ",").replace("Regola_In", " regola_in ")
    trasf = TRASFORMAZIONI_CSV.replace(";", ",") + "Note: riga non valida,,\n,,\n"
    conf = carica_configurazione(scrivi(tmp_path, "r.csv", regole, "cp1252"),
                                 scrivi(tmp_path, "t.csv", trasf, "cp1252"))
    assert converti("ITE-OT0B-1E-01-B1-BM", conf).nuova_sede_tecnica == "ITE-OT0B-1E-01-C1-R1"
    assert conf.avvisi and "8" in conf.avvisi[0]       # riga 8 del file scartata, riga 9 vuota ignorata


def test_errori_configurazione(tmp_path):
    regole = "Regola;Codice_Out\nA;B\n"
    trasf = "Segmento;Segmento;Espressione\n1;2;3\n"
    with pytest.raises(ErroreConfigurazione) as exc:
        carica_configurazione(scrivi(tmp_path, "r.csv", regole), scrivi(tmp_path, "t.csv", trasf))
    testo = str(exc.value)
    assert "Regola_In" in testo and "non trovata" in testo
    assert "presente più volte" in testo and "Valore_Atteso" in testo


def test_file_mancante(tmp_path):
    with pytest.raises(ErroreConfigurazione, match="File non trovato"):
        carica_configurazione(tmp_path / "manca.csv", tmp_path / "manca2.csv")


def test_dataframe(conf):
    df = pd.DataFrame({"Sede_tecnica": ["ITE-OT0B-1E-01-B1-BM", "ITE-OT0B-00", None,
                                        "ITE-OT0B-1E-01-B1-BM", "ITE-OT0B-0E-SA"]})
    out = elabora_dataframe(df, conf)
    assert list(out["Esito"]) == [ESITO_OK, ESITO_NESSUNA_CORRISPONDENZA, ESITO_VUOTA, ESITO_OK, ESITO_OK]
    assert out.loc[0, "Nuova_Sede_Tecnica"] == "ITE-OT0B-1E-01-C1-R1"
    assert out.loc[4, "Nuova_Sede_Tecnica"] == "ITE-OT0B-1A-S1"
    assert "Codice_Out" not in df.columns                         # l'originale non viene modificato
    assert riepilogo(out) == {ESITO_OK: 3, ESITO_DA_VERIFICARE: 0,
                              ESITO_NESSUNA_CORRISPONDENZA: 1, ESITO_VUOTA: 1}


def test_dataframe_colonna_mancante(conf):
    with pytest.raises(KeyError):
        elabora_dataframe(pd.DataFrame({"Altro": ["X"]}), conf)
