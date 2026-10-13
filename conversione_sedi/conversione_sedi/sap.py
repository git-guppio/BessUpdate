"""Estrazione dei dati da SAP tramite SAP GUI Scripting.

Funzioni principali:
    connetti_sessione()                 -> sessione SAP GUI già aperta dall'utente
    estrai_sedi_ih06(sessione, impianto) -> Sedi tecniche dell'impianto (tab Actual / Check)
    estrai_ordini_iw39(sessione, sedi)   -> Work Order aperti sulle Sedi indicate (tab No_Wo)
    estrai_avvisi_iw29(sessione, sedi)   -> Notification aperte sulle Sedi indicate (tab No_Wo)

Requisiti:
- SAP GUI aperto, con login effettuato in lingua italiana (i messaggi e gli
  stati di sistema vengono interpretati in italiano);
- scripting abilitato sul server e sul client;
- layout utente FL_BESS_MIG (IH06), OdM_BESS_MIG (IW39), AdM_BESS_MIG (IW29).

Se le funzioni vengono chiamate da un thread diverso da quello principale,
quel thread deve prima eseguire pythoncom.CoInitialize().

Tutti gli errori vengono segnalati con ErroreSAP, con messaggi in italiano.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from conversione_sedi import lista_sap
from conversione_sedi.lista_sap import (
    COL_AVVISO, COL_DESCRIZIONE, COL_ORDINE, COL_SEDE, COL_STATO, ErroreListaSAP,
)

# ---------------------------------------------------------------------------
# Identificativi degli elementi SAP GUI
# ---------------------------------------------------------------------------
ID_OKCODE = "wnd[0]/tbar[0]/okcd"
ID_BARRA_STATO = "wnd[0]/sbar"
ID_FINESTRA = "wnd[0]"
ID_POPUP = "wnd[1]"
ID_ESEGUI = "wnd[0]/tbar[1]/btn[8]"

ID_LAYOUT = "wnd[0]/usr/ctxtVARIANT"
ID_SEDE_DA = "wnd[0]/usr/ctxtSTRNO-LOW"
ID_DATA_DA = "wnd[0]/usr/ctxtDATUV"
ID_DATA_A = "wnd[0]/usr/ctxtDATUB"

# Selezione multipla delle Sedi tecniche
ID_SEL_MULTIPLA_SEDI = "wnd[0]/usr/btn%_STRNO_%_APP_%-VALU_PUSH"
ID_SEL_MULTIPLA_CANCELLA = "wnd[1]/tbar[0]/btn[16]"     # cancella l'intera selezione
ID_SEL_MULTIPLA_INCOLLA = "wnd[1]/tbar[0]/btn[24]"      # carica dagli appunti
ID_SEL_MULTIPLA_CONFERMA = "wnd[1]/tbar[0]/btn[8]"      # acquisisci

# Esportazione della lista negli appunti (Lista > Salva > File > "Negli appunti")
ID_EXPORT_APPUNTI = ("wnd[1]/usr/subSUBSCREEN_STEPLOOP:SAPLSPO5:0150/"
                     "sub:SAPLSPO5:0150/radSPOPLI-SELFLAG[4,0]")
ID_POPUP_CONFERMA = "wnd[1]/tbar[0]/btn[0]"

# Videata del singolo ordine (IW39 con un solo risultato)
_ORDINE = "wnd[0]/usr/subSUB_ALL:SAPLCOIH:3001/ssubSUB_LEVEL:SAPLCOIH:1100/"
CAMPI_ORDINE = {
    COL_ORDINE: _ORDINE + "subSUB_KOPF:SAPLCOIH:1102/txtCAUFVD-AUFNR",
    COL_DESCRIZIONE: _ORDINE + "subSUB_KOPF:SAPLCOIH:1102/txtCAUFVD-KTEXT",
    COL_SEDE: _ORDINE + "tabsTS_1100/tabpIHKZ/ssubSUB_AUFTRAG:SAPLCOIH:1120/"
                        "subOBJECT:SAPLCOIH:7120/ctxtCAUFVD-TPLNR",
    COL_STATO: "wnd[0]/usr/txtRILO0-STTXT",
}

# Videata del singolo avviso (IW29 con un solo risultato)
_AVVISO = "wnd[0]/usr/subSCREEN_1:SAPLIQS0:1050/"
CAMPI_AVVISO = {
    COL_AVVISO: _AVVISO + "txtVIQMEL-QMNUM",
    COL_DESCRIZIONE: _AVVISO + "subNOTIF_TYPE:SAPLIQS0:1051/txtVIQMEL-QMTXT",
    COL_SEDE: ("wnd[0]/usr/tabsTAB_GROUP_10/tabp10\\TAB01/ssubSUB_GROUP_10:SAPLIQS0:7235/"
               "subCUSTOM_SCREEN:SAPLIQS0:7212/subSUBSCREEN_1:SAPLIQS0:7322/"
               "subOBJEKT:SAPLIWO1:0120/ctxtRIWO1-TPLNR"),
    COL_STATO: "wnd[0]/usr/txtRILO0-STTXT",
}

MSG_NESSUN_OGGETTO = "non sono stati selezionati oggetti"
TIPI_ERRORE = ("E", "A")            # messaggi di errore e di interruzione
LINGUE_AMMESSE = ("IT", "I")


# ---------------------------------------------------------------------------
# Configurazione delle transazioni
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Transazione:
    codice: str
    layout: str
    menu_export: str
    colonne: tuple[str, ...]
    converti_lista: Callable[[str], pd.DataFrame]
    caselle: dict[str, bool] = field(default_factory=dict)
    azzera_date: bool = False
    campi_singolo: dict[str, str] | None = None     # videata del singolo oggetto


IH06 = Transazione(
    codice="IH06",
    layout="FL_BESS_MIG",
    menu_export="wnd[0]/mbar/menu[0]/menu[10]/menu[2]",
    colonne=(COL_SEDE, COL_DESCRIZIONE),
    converti_lista=lista_sap.sedi_da_ih06,
)

IW39 = Transazione(
    codice="IW39",
    layout="OdM_BESS_MIG",
    menu_export="wnd[0]/mbar/menu[0]/menu[11]/menu[2]",
    colonne=(COL_SEDE, COL_ORDINE, COL_DESCRIZIONE, COL_STATO),
    converti_lista=lista_sap.ordini_da_iw39,
    caselle={"wnd[0]/usr/chkDY_OFN": True,       # aperti
             "wnd[0]/usr/chkDY_IAR": True,       # in lavorazione
             "wnd[0]/usr/chkDY_MAB": False,      # chiusi
             "wnd[0]/usr/chkDY_HIS": True},      # storici
    azzera_date=True,
    campi_singolo=CAMPI_ORDINE,
)

IW29 = Transazione(
    codice="IW29",
    layout="AdM_BESS_MIG",
    menu_export="wnd[0]/mbar/menu[0]/menu[11]/menu[2]",
    colonne=(COL_SEDE, COL_AVVISO, COL_DESCRIZIONE, COL_STATO),
    converti_lista=lista_sap.avvisi_da_iw29,
    caselle={"wnd[0]/usr/chkDY_OFN": True,       # aperti
             "wnd[0]/usr/chkDY_RST": True,       # rinviati
             "wnd[0]/usr/chkDY_IAR": True,       # in lavorazione
             "wnd[0]/usr/chkDY_MAB": False},     # chiusi
    azzera_date=True,
    campi_singolo=CAMPI_AVVISO,
)


class ErroreSAP(Exception):
    """Errore nella comunicazione con SAP o nell'esecuzione di una transazione."""


# ---------------------------------------------------------------------------
# Appunti di Windows
# ---------------------------------------------------------------------------
def _apri_appunti(tentativi: int = 10) -> None:
    import win32clipboard
    for _ in range(tentativi):
        try:
            win32clipboard.OpenClipboard()
            return
        except Exception:
            time.sleep(0.1)                     # appunti occupati da un altro programma
    raise ErroreSAP("Impossibile accedere agli appunti di Windows.")


def leggi_appunti() -> str:
    import win32clipboard
    _apri_appunti()
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
            return win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        return ""
    finally:
        win32clipboard.CloseClipboard()


def scrivi_appunti(testo: str) -> None:
    import win32clipboard
    _apri_appunti()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(testo, win32clipboard.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()


@contextmanager
def _appunti_conservati():
    """Ripristino del contenuto testuale degli appunti dell'utente al termine."""
    try:
        precedente = leggi_appunti()
    except ErroreSAP:
        precedente = None
    try:
        yield
    finally:
        if precedente is not None:
            try:
                scrivi_appunti(precedente)
            except ErroreSAP:
                pass


# ---------------------------------------------------------------------------
# Connessione
# ---------------------------------------------------------------------------
def connetti_sessione(indice_connessione: int = 0, indice_sessione: int = 0) -> Any:
    """Aggancio alla sessione SAP GUI aperta dall'utente."""
    import win32com.client

    try:
        sap_gui = win32com.client.GetObject("SAPGUI")
    except Exception:
        raise ErroreSAP("SAP GUI non è in esecuzione: aprire SAP ed effettuare il login.") from None
    try:
        applicazione = sap_gui.GetScriptingEngine
    except Exception:
        raise ErroreSAP("SAP GUI Scripting non disponibile: verificare che sia abilitato "
                        "nelle opzioni di SAP GUI.") from None

    if applicazione.Children.Count <= indice_connessione:
        raise ErroreSAP("Nessuna connessione SAP aperta: effettuare il login.")
    connessione = applicazione.Children(indice_connessione)
    if getattr(connessione, "DisabledByServer", False):
        raise ErroreSAP("SAP GUI Scripting è disabilitato sul server SAP.")
    if connessione.Children.Count <= indice_sessione:
        raise ErroreSAP("Nessuna sessione SAP disponibile: effettuare il login.")
    sessione = connessione.Children(indice_sessione)

    if sessione.Busy:
        raise ErroreSAP("La sessione SAP è occupata: attendere il termine dell'operazione in corso.")
    lingua = str(sessione.Info.Language).upper()
    if lingua not in LINGUE_AMMESSE:
        raise ErroreSAP(f"SAP deve essere utilizzato in lingua italiana (lingua attuale: {lingua}).")
    return sessione


# ---------------------------------------------------------------------------
# Funzioni di supporto
# ---------------------------------------------------------------------------
def _esiste(sessione, id_elemento: str) -> bool:
    try:
        return sessione.findById(id_elemento, False) is not None
    except Exception:
        return False


def _elemento(sessione, id_elemento: str, transazione: str):
    try:
        return sessione.findById(id_elemento)
    except Exception:
        raise ErroreSAP(f"{transazione}: elemento della videata non trovato ({id_elemento}). "
                        "La videata SAP potrebbe essere cambiata.") from None


def _barra_stato(sessione) -> tuple[str, str]:
    """(tipo, testo) del messaggio nella barra di stato.
    Tipi: S successo, W avviso, E errore, A interruzione, I informazione, "" nessuno."""
    try:
        barra = sessione.findById(ID_BARRA_STATO)
        return str(barra.messageType or ""), str(barra.text or "").strip()
    except Exception:
        return "", ""


def _controlla_errori(sessione, transazione: str) -> str:
    """ErroreSAP se la barra di stato contiene un errore o se è comparsa una
    finestra di dialogo inattesa. Restituisce il testo della barra di stato."""
    tipo, testo = _barra_stato(sessione)
    if tipo in TIPI_ERRORE:
        raise ErroreSAP(f"{transazione}: {testo}")
    if _esiste(sessione, ID_POPUP):
        titolo = str(getattr(sessione.findById(ID_POPUP), "text", "")).strip()
        raise ErroreSAP(f"{transazione}: finestra inattesa \"{titolo}\".")
    return testo


def _chiudi_popup(sessione) -> None:
    for _ in range(5):
        if not _esiste(sessione, ID_POPUP):
            return
        try:
            sessione.findById(ID_POPUP).close()
        except Exception:
            return


def _comando(sessione, comando: str) -> None:
    sessione.findById(ID_OKCODE).text = comando
    sessione.findById(ID_FINESTRA).sendVKey(0)


def _invio(sessione) -> None:
    sessione.findById(ID_FINESTRA).sendVKey(0)


def _incolla_selezione_multipla(sessione, valori: list[str], transazione: str) -> None:
    """Inserimento delle Sedi tecniche nella selezione multipla tramite appunti."""
    scrivi_appunti("\r\n".join(valori))
    _elemento(sessione, ID_SEL_MULTIPLA_SEDI, transazione).press()
    _elemento(sessione, ID_SEL_MULTIPLA_CANCELLA, transazione).press()
    _elemento(sessione, ID_SEL_MULTIPLA_INCOLLA, transazione).press()
    _elemento(sessione, ID_SEL_MULTIPLA_CONFERMA, transazione).press()
    _controlla_errori(sessione, transazione)


def _leggi_singolo(sessione, campi: dict[str, str], transazione: str) -> dict[str, str]:
    return {col: str(_elemento(sessione, id_, transazione).text).strip()
            for col, id_ in campi.items()}


def _esporta_lista(sessione, conf: Transazione) -> pd.DataFrame:
    scrivi_appunti("")                          # evita di leggere contenuti precedenti
    _elemento(sessione, conf.menu_export, conf.codice).select()
    _elemento(sessione, ID_EXPORT_APPUNTI, conf.codice).select()
    _elemento(sessione, ID_POPUP_CONFERMA, conf.codice).press()
    _controlla_errori(sessione, conf.codice)
    testo = leggi_appunti()
    if not testo.strip():
        raise ErroreSAP(f"{conf.codice}: la lista esportata negli appunti è vuota.")
    try:
        return conf.converti_lista(testo)
    except ErroreListaSAP as e:
        messaggio = str(e)
        if not messaggio.startswith(conf.codice):
            messaggio = f"{conf.codice}: {messaggio}"
        raise ErroreSAP(messaggio) from None


def _vuoto(conf: Transazione) -> pd.DataFrame:
    return pd.DataFrame(columns=list(conf.colonne), dtype=str)


# ---------------------------------------------------------------------------
# Esecuzione di una transazione
# ---------------------------------------------------------------------------
def _esegui(sessione, conf: Transazione, *, sede_da: str | None = None,
            sedi: list[str] | None = None) -> pd.DataFrame:
    with _appunti_conservati():
        try:
            _comando(sessione, f"/n{conf.codice}")
            _controlla_errori(sessione, conf.codice)

            # schermata di selezione
            for id_casella, valore in conf.caselle.items():
                _elemento(sessione, id_casella, conf.codice).selected = valore
            if sedi is not None:
                _incolla_selezione_multipla(sessione, sedi, conf.codice)
            if sede_da is not None:
                _elemento(sessione, ID_SEDE_DA, conf.codice).text = sede_da
            if conf.azzera_date:
                _elemento(sessione, ID_DATA_DA, conf.codice).text = ""
                _elemento(sessione, ID_DATA_A, conf.codice).text = ""
            _elemento(sessione, ID_LAYOUT, conf.codice).text = conf.layout
            _invio(sessione)
            _controlla_errori(sessione, conf.codice)        # es. layout inesistente

            # esecuzione
            _elemento(sessione, ID_ESEGUI, conf.codice).press()
            tipo, testo = _barra_stato(sessione)
            if MSG_NESSUN_OGGETTO in testo.lower():
                return _vuoto(conf)
            _controlla_errori(sessione, conf.codice)
            if _esiste(sessione, ID_LAYOUT):                # ancora sulla selezione
                raise ErroreSAP(f"{conf.codice}: estrazione non eseguita. {testo}".strip())

            # un solo risultato: SAP apre direttamente l'oggetto
            if conf.campi_singolo and _esiste(sessione, next(iter(conf.campi_singolo.values()))):
                riga = _leggi_singolo(sessione, conf.campi_singolo, conf.codice)
                return pd.DataFrame([riga], columns=list(conf.colonne), dtype=str)

            df = _esporta_lista(sessione, conf)
            return df[list(conf.colonne)].reset_index(drop=True)
        finally:
            try:
                _chiudi_popup(sessione)
                _comando(sessione, "/n")
            except Exception:
                pass


def _normalizza_sedi(sedi) -> list[str]:
    visti, out = set(), []
    for s in sedi:
        s = str(s or "").strip().upper()
        if s and s not in visti:
            visti.add(s)
            out.append(s)
    return out


def estrai_sedi_ih06(sessione, impianto: str) -> pd.DataFrame:
    """Sedi tecniche dell'impianto con colonne Sede tecnica e Descrizione,
    escluse quelle con stato CANC, OGIN o FCAN.

    L'impianto si può indicare con o senza asterisco ("USE-USS5" o "USE-USS5*"):
    nel campo Sede tecnica di IH06 viene sempre inserito "USE-USS5*", così da
    estrarre l'impianto e tutte le Sedi tecniche sottostanti."""
    impianto = str(impianto or "").strip().upper().removesuffix("*")
    if len(impianto.split("-")) != 2 or not all(impianto.split("-")) or "*" in impianto:
        raise ErroreSAP(f"Impianto non valido: \"{impianto}\" (atteso, ad esempio, \"USE-USS5\").")
    df = _esegui(sessione, IH06, sede_da=f"{impianto}*")
    estranee = [s for s in df[COL_SEDE] if not (s == impianto or s.startswith(impianto + "-"))]
    if estranee:
        raise ErroreSAP(f"IH06: estratte Sedi tecniche di altri impianti (es. {estranee[0]}).")
    return df


def estrai_ordini_iw39(sessione, sedi) -> pd.DataFrame:
    """Work Order non chiusi sulle Sedi tecniche indicate
    (colonne Sede tecnica, Work Order, Descrizione, Stato)."""
    sedi = _normalizza_sedi(sedi)
    if not sedi:
        return _vuoto(IW39)
    return _esegui(sessione, IW39, sedi=sedi)


def estrai_avvisi_iw29(sessione, sedi) -> pd.DataFrame:
    """Notification non chiuse sulle Sedi tecniche indicate
    (colonne Sede tecnica, Notification, Descrizione, Stato)."""
    sedi = _normalizza_sedi(sedi)
    if not sedi:
        return _vuoto(IW29)
    return _esegui(sessione, IW29, sedi=sedi)
