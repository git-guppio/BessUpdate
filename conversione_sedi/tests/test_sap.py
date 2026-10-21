"""Test del modulo sap con una sessione SAP GUI simulata (nessun accesso a SAP)."""
from pathlib import Path

import pytest

from conversione_sedi import sap
from conversione_sedi.sap import (
    ID_BARRA_STATO, ID_DATA_A, ID_DATA_DA, ID_ESEGUI, ID_EXPORT_APPUNTI, ID_FINESTRA, ID_LAYOUT,
    ID_OKCODE, ID_POPUP, ID_POPUP_CONFERMA, ID_SEDE_DA, ID_SEL_MULTIPLA_CANCELLA,
    ID_SEL_MULTIPLA_CONFERMA, ID_SEL_MULTIPLA_INCOLLA, ID_SEL_MULTIPLA_SEDI, IH06, IW29, IW39,
    ErroreSAP, estrai_avvisi_iw29, estrai_ordini_iw39, estrai_sedi_ih06,
)

DATI = Path(__file__).parent / "dati"
TRANSAZIONI = {"IH06": IH06, "IW39": IW39, "IW29": IW29}


# ---------------------------------------------------------------------------
# Sessione simulata
# ---------------------------------------------------------------------------
class Elemento:
    def __init__(self, sessione, id_):
        self.sessione, self.id = sessione, id_
        self.text, self.selected, self.messageType = "", False, ""

    def press(self):
        self.sessione.evento("press", self.id)

    def select(self):
        self.sessione.evento("select", self.id)

    def sendVKey(self, tasto):
        self.sessione.evento("invio", self.id)

    def close(self):
        self.sessione.elementi.pop(self.id, None)


class SessioneFinta:
    """Simula le videate: selezione -> (lista | singolo | nessun risultato | errore)."""

    def __init__(self, esito="lista", testo_lista="", singolo=None, errore_invio="",
                 popup_dopo_esecuzione=False, messaggio_vuoto=("S", "Non sono stati selezionati oggetti")):
        self.esito, self.testo_lista, self.singolo = esito, testo_lista, singolo or {}
        self.errore_invio, self.popup_dopo_esecuzione = errore_invio, popup_dopo_esecuzione
        self.messaggio_vuoto = messaggio_vuoto
        self.elementi, self.comandi, self.transazione = {}, [], None
        self.aggiungi(ID_OKCODE, ID_FINESTRA, ID_BARRA_STATO)

    def aggiungi(self, *ids):
        for id_ in ids:
            self.elementi.setdefault(id_, Elemento(self, id_))

    def findById(self, id_, solleva=True):
        if id_ in self.elementi:
            return self.elementi[id_]
        if solleva:
            raise Exception(f"elemento {id_} non trovato")
        return None

    def barra(self, tipo="", testo=""):
        b = self.elementi[ID_BARRA_STATO]
        b.messageType, b.text = tipo, testo

    def evento(self, tipo, id_):
        self.barra()
        if tipo == "invio" and id_ == ID_FINESTRA:
            comando = self.elementi[ID_OKCODE].text
            self.elementi[ID_OKCODE].text = ""
            if comando:
                self.comandi.append(comando)
                self._apri(comando[2:].upper())
            elif self.errore_invio:
                self.barra("E", self.errore_invio)
        elif tipo == "press" and id_ == ID_ESEGUI:
            self._esegui()
        elif tipo == "press" and id_ == ID_POPUP_CONFERMA:
            APPUNTI["testo"] = self.testo_lista
            self.barra("S", "Lista trasferita negli appunti")

    def _apri(self, codice):
        self.elementi = {k: v for k, v in self.elementi.items()
                         if k in (ID_OKCODE, ID_FINESTRA, ID_BARRA_STATO)}
        self.transazione = TRANSAZIONI.get(codice)
        if self.transazione:
            conf = self.transazione
            self.aggiungi(ID_LAYOUT, ID_ESEGUI, ID_SEDE_DA, ID_DATA_DA, ID_DATA_A,
                          ID_SEL_MULTIPLA_SEDI, ID_SEL_MULTIPLA_CANCELLA,
                          ID_SEL_MULTIPLA_INCOLLA, ID_SEL_MULTIPLA_CONFERMA, *conf.caselle)
            for id_ in (ID_DATA_DA, ID_DATA_A):
                self.elementi[id_].text = "01.01.2026"

    def _esegui(self):
        self.selezione = {k: (v.text, v.selected) for k, v in self.elementi.items()}
        conf = self.transazione
        if self.esito == "vuoto":
            self.barra(*self.messaggio_vuoto)
            return
        if self.esito == "errore":
            self.barra("E", "Autorizzazione mancante per la transazione")
            return
        del self.elementi[ID_LAYOUT]
        if self.esito == "singolo":
            for col, id_ in conf.campi_singolo.items():
                self.aggiungi(id_)
                self.elementi[id_].text = self.singolo[col]
        else:
            self.aggiungi(conf.menu_export, ID_EXPORT_APPUNTI, ID_POPUP_CONFERMA)
        if self.popup_dopo_esecuzione:
            self.aggiungi(ID_POPUP)
            self.elementi[ID_POPUP].text = "Informazione"


APPUNTI = {"testo": ""}


@pytest.fixture(autouse=True)
def appunti_finti(monkeypatch):
    APPUNTI["testo"] = "contenuto dell'utente"
    APPUNTI["scritture"] = []

    def scrivi(testo):
        APPUNTI["testo"] = testo
        APPUNTI["scritture"].append(testo)

    monkeypatch.setattr(sap, "leggi_appunti", lambda: APPUNTI["testo"])
    monkeypatch.setattr(sap, "scrivi_appunti", scrivi)


def esempio(nome):
    return (DATI / nome).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# IH06
# ---------------------------------------------------------------------------
def test_ih06_lista():
    s = SessioneFinta(testo_lista=esempio("TestoAppunti_IH06.txt"))
    df = estrai_sedi_ih06(s, " use-uss5 ")
    assert list(df.columns) == ["Sede tecnica", "Descrizione"] and len(df) == 1782
    assert s.selezione[ID_SEDE_DA][0] == "USE-USS5*"
    assert s.selezione[ID_LAYOUT][0] == "FL_BESS_MIG"
    assert s.comandi == ["/nIH06", "/n"]                       # ritorno alla videata iniziale
    assert APPUNTI["testo"] == "contenuto dell'utente"          # appunti dell'utente ripristinati


@pytest.mark.parametrize("impianto", ["USE-USS5", "use-uss5*", " USE-USS5* "])
def test_ih06_impianto_con_o_senza_asterisco(impianto):
    s = SessioneFinta(testo_lista=esempio("TestoAppunti_IH06.txt"))
    estrai_sedi_ih06(s, impianto)
    assert s.selezione[ID_SEDE_DA][0] == "USE-USS5*"


@pytest.mark.parametrize("impianto", ["", "*", "USE", "USE-USS5-1E", "USE-*", "USE-", "USE-US*5"])
def test_ih06_impianto_non_valido(impianto):
    with pytest.raises(ErroreSAP, match="Impianto non valido"):
        estrai_sedi_ih06(SessioneFinta(), impianto)


def test_ih06_sedi_di_altri_impianti():
    s = SessioneFinta(testo_lista=esempio("TestoAppunti_IH06.txt"))
    with pytest.raises(ErroreSAP, match="altri impianti"):
        estrai_sedi_ih06(s, "USE-USS")          # "USE-USS*" estrae anche USE-USS5


# ---------------------------------------------------------------------------
# IW39 / IW29
# ---------------------------------------------------------------------------
def test_iw39_lista():
    s = SessioneFinta(testo_lista=esempio("TestoAppunti_IW39.txt"))
    df = estrai_ordini_iw39(s, ["use-uss5-00-oc", "USE-USS5-1A-S1-DG", "USE-USS5-00-OC", ""])
    assert len(df) == 15
    assert list(df.columns) == ["Sede tecnica", "Work Order", "Descrizione", "Stato"]
    # sedi normalizzate, senza duplicati, passate alla selezione multipla
    assert APPUNTI["scritture"][0] == "USE-USS5-00-OC\r\nUSE-USS5-1A-S1-DG"
    assert s.selezione["wnd[0]/usr/chkDY_MAB"][1] is False      # chiusi esclusi
    assert s.selezione["wnd[0]/usr/chkDY_OFN"][1] is True
    assert s.selezione[ID_DATA_DA][0] == "" and s.selezione[ID_DATA_A][0] == ""
    assert s.selezione[ID_LAYOUT][0] == "OdM_BESS_MIG"


def test_iw39_singolo_ordine():
    singolo = {"Work Order": "210001737613", "Descrizione": "BOP_Monthly_SPCC",
               "Sede tecnica": "USE-USS5-00-OC", "Stato": "RIL. CALP"}
    df = estrai_ordini_iw39(SessioneFinta(esito="singolo", singolo=singolo), ["USE-USS5-00-OC"])
    assert df.to_dict("records") == [{"Sede tecnica": "USE-USS5-00-OC", "Work Order": "210001737613",
                                      "Descrizione": "BOP_Monthly_SPCC", "Stato": "RIL. CALP"}]


def test_iw29_lista():
    s = SessioneFinta(testo_lista=esempio("TestoAppunti_IW29.txt"))
    df = estrai_avvisi_iw29(s, ["USE-USS5-1A-CS"])
    assert df["Notification"].tolist() == ["1100110930", "1200927446", "1200902385"]
    assert s.selezione["wnd[0]/usr/chkDY_RST"][1] is True
    assert s.selezione[ID_LAYOUT][0] == "AdM_BESS_MIG"


def test_iw29_singolo_avviso():
    singolo = {"Notification": "1200927446", "Descrizione": "BESS support pictures",
               "Sede tecnica": "USE-USS5-1A-CS", "Stato": "MELA ORAT"}
    df = estrai_avvisi_iw29(SessioneFinta(esito="singolo", singolo=singolo), ["USE-USS5-1A-CS"])
    assert df.loc[0, "Notification"] == "1200927446" and df.loc[0, "Stato"] == "MELA ORAT"


def test_nessun_risultato():
    s = SessioneFinta(esito="vuoto")
    df = estrai_avvisi_iw29(s, ["USE-USS5-1A-CS"])
    assert df.empty and list(df.columns) == ["Sede tecnica", "Notification", "Descrizione", "Stato"]
    assert s.comandi[-1] == "/n"


@pytest.mark.parametrize("tipo, testo", [
    ("S", "Non sono stati selezionati oggetti"),
    ("E", "Non sono stati selezionati oggetti"),             # anche se SAP lo segnala come errore
    ("W", "non sono stati selezionati oggetti."),
    ("I", "  Non sono  stati selezionati   oggetti  "),
])
def test_nessun_oggetto_varianti(tipo, testo):
    for estrai in (estrai_ordini_iw39, estrai_avvisi_iw29):
        s = SessioneFinta(esito="vuoto", messaggio_vuoto=(tipo, testo))
        assert estrai(s, ["USE-USS5-1A-CS"]).empty
        assert s.comandi[-1] == "/n"


def test_nessun_oggetto_costante_indipendente_dalle_maiuscole(monkeypatch):
    from conversione_sedi.sap import nessun_oggetto
    for costante in ("Non sono stati selezionati oggetti", "non sono stati selezionati oggetti"):
        monkeypatch.setattr(sap, "MSG_NESSUN_OGGETTO", costante)
        assert nessun_oggetto("Non sono stati selezionati oggetti")
        assert not nessun_oggetto("Autorizzazione mancante")


def test_nessuna_sede_nessuna_chiamata():
    s = SessioneFinta()
    assert estrai_ordini_iw39(s, []).empty
    assert s.comandi == []


# ---------------------------------------------------------------------------
# Errori
# ---------------------------------------------------------------------------
def test_errore_barra_di_stato():
    s = SessioneFinta(esito="errore")
    with pytest.raises(ErroreSAP, match="IW39: Autorizzazione mancante"):
        estrai_ordini_iw39(s, ["USE-USS5-00-OC"])
    assert s.comandi[-1] == "/n"


def test_layout_inesistente():
    s = SessioneFinta(errore_invio="Il layout OdM_BESS_MIG non esiste")
    with pytest.raises(ErroreSAP, match="layout OdM_BESS_MIG non esiste"):
        estrai_ordini_iw39(s, ["USE-USS5-00-OC"])


def test_finestra_inattesa():
    s = SessioneFinta(testo_lista=esempio("TestoAppunti_IW29.txt"), popup_dopo_esecuzione=True)
    with pytest.raises(ErroreSAP, match="finestra inattesa \"Informazione\""):
        estrai_avvisi_iw29(s, ["USE-USS5-1A-CS"])
    assert ID_POPUP not in s.elementi                           # finestra chiusa all'uscita


def test_lista_esportata_vuota():
    s = SessioneFinta(testo_lista="")
    with pytest.raises(ErroreSAP, match="lista esportata negli appunti è vuota"):
        estrai_sedi_ih06(s, "USE-USS5")


def test_layout_senza_colonne_attese():
    s = SessioneFinta(testo_lista="|Ordine|Descrizione|\n|1|x|\n")
    with pytest.raises(ErroreSAP, match=r"^IW39: colonne non trovate: \"Sede tecnica\""):
        estrai_ordini_iw39(s, ["USE-USS5-00-OC"])


def test_videata_cambiata():
    s = SessioneFinta(testo_lista="x")
    s._apri_originale = s._apri

    def apri_senza_layout(codice):
        s._apri_originale(codice)
        del s.elementi[ID_LAYOUT]

    s._apri = apri_senza_layout
    with pytest.raises(ErroreSAP, match="elemento della videata non trovato .*ctxtVARIANT"):
        estrai_sedi_ih06(s, "USE-USS5")


# ---------------------------------------------------------------------------
# Singolo oggetto: campo cercato per nome tecnico se l'identificativo manca
# ---------------------------------------------------------------------------
class Collezione:
    def __init__(self, elementi):
        self._e = list(elementi)
        self.Count = len(self._e)

    def ElementAt(self, i):
        return self._e[i]


class Nodo:
    def __init__(self, nome="", text="", figli=(), tipo=None, id_=None):
        self.Name, self.text = nome, text
        if tipo != "":                                       # tipo "" = proprietà Type assente
            self.Type = tipo or ("GuiSimpleContainer" if figli else "GuiTextField")
        if id_:
            self.Id = id_
        if figli:
            self.Children = Collezione(figli)


def sessione_con_videata(conf, valori, mancanti, videata):
    s = SessioneFinta(esito="singolo", singolo=valori)
    originale = s._esegui

    def esegui():
        originale()
        for col in mancanti:
            s.elementi.pop(conf.campi_singolo[col], None)
        s.elementi["wnd[0]/usr"] = videata

    s._esegui = esegui
    return s


def test_avviso_singolo_stato_cercato_per_nome():
    valori = {"Notification": "1200927446", "Descrizione": "BESS support pictures",
              "Sede tecnica": "USE-USS5-1A-CS", "Stato": "non usato"}
    videata = Nodo("usr", figli=[
        Nodo("subSCREEN_1", figli=[
            Nodo("VIQMEL-QMNUM", "1200927446"),
            Nodo("RIWO00-STTXT", "Stato avviso", tipo="GuiLabel"),      # etichetta: va scartata
            Nodo("subSTATUS", figli=[Nodo("RIWO00-STTXT", "MELA ORAT")]),
        ]),
        Nodo("RIWO00-ASTTX", "stato utente"),
    ])
    s = sessione_con_videata(IW29, valori, ["Stato"], videata)
    df = estrai_avvisi_iw29(s, ["USE-USS5-1A-CS"])
    assert df.loc[0, "Stato"] == "MELA ORAT" and df.loc[0, "Notification"] == "1200927446"


def test_ordine_singolo_sede_e_stato_cercati_per_nome():
    valori = {"Work Order": "210001737613", "Descrizione": "BOP", "Sede tecnica": "x", "Stato": "x"}
    videata = Nodo("usr", figli=[Nodo("CAUFVD-STTXT", "RIL. CALP"), Nodo("CAUFVD-TPLNR", "USE-USS5-00-OC")])
    s = sessione_con_videata(IW39, valori, ["Stato", "Sede tecnica"], videata)
    df = estrai_ordini_iw39(s, ["USE-USS5-00-OC"])
    assert df.loc[0, ["Sede tecnica", "Stato"]].tolist() == ["USE-USS5-00-OC", "RIL. CALP"]


def test_campo_singolo_introvabile():
    valori = {"Notification": "1", "Descrizione": "d", "Sede tecnica": "s", "Stato": "x"}
    s = sessione_con_videata(IW29, valori, ["Stato"], Nodo("usr", figli=[Nodo("ALTRO", "y")]))
    with pytest.raises(ErroreSAP, match=r"campo \"Stato\" non trovato.*\*-STTXT"):
        estrai_avvisi_iw29(s, ["USE-USS5-1A-CS"])


def test_avviso_singolo_id_configurato():
    from conversione_sedi.sap import CAMPI_AVVISO
    assert CAMPI_AVVISO["Stato"] == "wnd[0]/usr/subSCREEN_1:SAPLIQS0:1050/txtRIWO00-STTXT"


def test_etichetta_scartata_anche_senza_tipo():
    # se la proprietà Type non è disponibile si usa il prefisso dell'ID (lbl / txt)
    valori = {"Notification": "1", "Descrizione": "d", "Sede tecnica": "s", "Stato": "x"}
    videata = Nodo("usr", figli=[
        Nodo("RIWO00-STTXT", "Stato avviso", tipo="", id_="/app/con[0]/ses[0]/wnd[0]/usr/lblRIWO00-STTXT"),
        Nodo("RIWO00-STTXT", "MELA", tipo="", id_="/app/con[0]/ses[0]/wnd[0]/usr/txtRIWO00-STTXT"),
    ])
    s = sessione_con_videata(IW29, valori, ["Stato"], videata)
    assert estrai_avvisi_iw29(s, ["USE-USS5-1A-CS"]).loc[0, "Stato"] == "MELA"
