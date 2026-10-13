"""Nucleo di conversione Sede_tecnica -> Codice_Out -> Nuova_Sede_Tecnica.

Implementazione di riferimento, equivalente al modulo VBA modNuovoCodice.

Fase 1: individuazione della Regola_In verificata dalla Sede_tecnica e
        lettura del Codice_Out corrispondente.
Fase 2: elaborazione del Codice_Out tramite le regole di trasformazione.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------
CAR_JOLLY = "+"
CLASSE_JOLLY = "[A-Z0-9]"          # il jolly corrisponde a un solo carattere alfanumerico
SEP = "-"
PREFISSO_VERIFICA = "DA VERIFICARE: "

COLONNE_REGOLE = ("Regola_In", "Codice_Out")
COLONNE_TRASFORMAZIONI = ("Segmento", "Valore_Atteso", "Espressione")

ESITO_OK = "OK"
ESITO_DA_VERIFICARE = "DA_VERIFICARE"
ESITO_NESSUNA_CORRISPONDENZA = "NESSUNA_CORRISPONDENZA"
ESITO_VUOTA = "VUOTA"

_RE_RIFERIMENTO = re.compile(r"S(\d{1,5})(?:\.(\d{1,5})(?:-(\d{1,5}))?)?")
_RE_INTERO = re.compile(r"[0-9]{1,5}")
_RE_SEGNAPOSTO = re.compile(r"[+a-z]")


# ---------------------------------------------------------------------------
# Strutture dati
# ---------------------------------------------------------------------------
class ErroreConfigurazione(Exception):
    """Errore bloccante nella lettura dei file delle regole."""

    def __init__(self, errori: list[str]):
        self.errori = list(errori)
        super().__init__("\n".join(self.errori))


@dataclass(frozen=True)
class Regola:
    regola_in: str          # Regola_In normalizzata (maiuscolo, senza spazi esterni)
    codice_out: str         # Codice_Out tal quale (solo spazi esterni rimossi)
    pattern: re.Pattern
    num_jolly: int
    ordine: int             # posizione nel file (0 = prima regola)


@dataclass(frozen=True)
class Trasformazione:
    segmento: int           # posizione del segmento del Codice_Out (da 1)
    valore_atteso: str      # "" = regola sempre valida
    espressione: str


@dataclass
class Configurazione:
    # Regole raggruppate per lunghezza e ordinate per (num_jolly, ordine):
    # la prima che corrisponde è quella da applicare.
    regole_per_lunghezza: dict[int, list[Regola]]
    # Trasformazioni raggruppate per segmento, nell'ordine del file.
    trasformazioni: dict[int, list[Trasformazione]]
    avvisi: list[str] = field(default_factory=list)

    @property
    def num_regole(self) -> int:
        return sum(len(v) for v in self.regole_per_lunghezza.values())

    @property
    def num_trasformazioni(self) -> int:
        return sum(len(v) for v in self.trasformazioni.values())


@dataclass(frozen=True)
class Risultato:
    codice_out: str | None
    nuova_sede_tecnica: str | None
    esito: str


# ---------------------------------------------------------------------------
# Funzioni di supporto
# ---------------------------------------------------------------------------
def normalizza(valore: Any) -> str:
    """Rimozione degli spazi esterni e conversione in maiuscolo.
    None e NaN diventano stringa vuota."""
    if valore is None:
        return ""
    try:
        if pd.isna(valore):
            return ""
    except (TypeError, ValueError):
        pass
    return str(valore).strip().upper()


def compila_regola_in(regola_in: str) -> tuple[re.Pattern, int]:
    """Conversione della Regola_In in espressione regolare.
    Ogni "+" diventa [A-Z0-9]; tutti gli altri caratteri sono letterali."""
    parti, num_jolly = [], 0
    for c in regola_in:
        if c == CAR_JOLLY:
            parti.append(CLASSE_JOLLY)
            num_jolly += 1
        else:
            parti.append(re.escape(c))
    return re.compile("".join(parti)), num_jolly


def leggi_csv(percorso: str | Path) -> pd.DataFrame:
    """Lettura di un CSV come testo puro.
    - codifica: UTF-8 (anche con BOM), in alternativa Windows-1252;
    - separatore: ";" o "," rilevato dalla riga di intestazione;
    - nessuna conversione di tipo né interpretazione di NA (es. "nn", "NA")."""
    percorso = Path(percorso)
    if not percorso.is_file():
        raise ErroreConfigurazione([f"File non trovato: {percorso}"])

    testo = None
    for codifica in ("utf-8-sig", "cp1252"):
        try:
            testo = percorso.read_text(encoding=codifica)
            break
        except UnicodeDecodeError:
            continue
    if not testo or not testo.strip():
        raise ErroreConfigurazione([f"Il file {percorso.name} è vuoto."])

    intestazione = testo.splitlines()[0]
    sep = ";" if intestazione.count(";") >= intestazione.count(",") else ","
    df = pd.read_csv(io.StringIO(testo), sep=sep, dtype=str,
                     keep_default_na=False, na_filter=False)
    # pandas rinomina le intestazioni duplicate (es. "Segmento.1"): vengono
    # ripristinati i nomi originali, così da poter segnalare i duplicati.
    nomi_originali = next(csv.reader([intestazione], delimiter=sep))
    if len(nomi_originali) == len(df.columns):
        df.columns = nomi_originali
    return df


def trova_colonne(df: pd.DataFrame, attese: tuple[str, ...], nome_file: str) -> dict[str, str]:
    """Individuazione delle colonne attese (confronto senza distinzione tra
    maiuscole e minuscole e senza spazi esterni). Le colonne in più vengono
    ignorate. Restituisce {nome_atteso: nome_effettivo}."""
    errori, mappa = [], {}
    for nome in attese:
        trovate = [c for c in df.columns if str(c).strip().casefold() == nome.casefold()]
        if not trovate:
            errori.append(f"{nome_file}: intestazione \"{nome}\" non trovata.")
        elif len(trovate) > 1:
            errori.append(f"{nome_file}: intestazione \"{nome}\" presente più volte.")
        else:
            mappa[nome] = trovate[0]
    if errori:
        raise ErroreConfigurazione(errori)
    return mappa


# ---------------------------------------------------------------------------
# Caricamento della configurazione
# ---------------------------------------------------------------------------
def carica_regole(percorso: str | Path) -> dict[int, list[Regola]]:
    percorso = Path(percorso)
    df = leggi_csv(percorso)
    col = trova_colonne(df, COLONNE_REGOLE, percorso.name)

    regole: list[Regola] = []
    for ordine, (ri, co) in enumerate(zip(df[col["Regola_In"]], df[col["Codice_Out"]])):
        regola_in = normalizza(ri)
        if not regola_in:
            continue
        pattern, num_jolly = compila_regola_in(regola_in)
        regole.append(Regola(regola_in, str(co).strip(), pattern, num_jolly, ordine))

    if not regole:
        raise ErroreConfigurazione([f"{percorso.name}: nessuna regola valida."])

    per_lunghezza: dict[int, list[Regola]] = {}
    for r in regole:
        per_lunghezza.setdefault(len(r.regola_in), []).append(r)
    for lista in per_lunghezza.values():
        lista.sort(key=lambda r: (r.num_jolly, r.ordine))
    return per_lunghezza


def carica_trasformazioni(percorso: str | Path) -> tuple[dict[int, list[Trasformazione]], list[str]]:
    percorso = Path(percorso)
    df = leggi_csv(percorso)
    col = trova_colonne(df, COLONNE_TRASFORMAZIONI, percorso.name)

    trasformazioni: dict[int, list[Trasformazione]] = {}
    righe_scartate: list[int] = []
    valori = zip(df[col["Segmento"]], df[col["Valore_Atteso"]], df[col["Espressione"]])
    for indice, (seg, att, esp) in enumerate(valori):
        seg, att, esp = str(seg).strip(), str(att).strip(), str(esp).strip()
        if not seg and not att and not esp:
            continue                                    # riga vuota
        if _RE_INTERO.fullmatch(seg) and int(seg) >= 1 and esp:
            atteso = "" if att == "*" else att
            trasformazioni.setdefault(int(seg), []).append(Trasformazione(int(seg), atteso, esp))
        else:
            righe_scartate.append(indice + 2)               # riga del file (1 = intestazione)

    avvisi = []
    if righe_scartate:
        avvisi.append(f"{percorso.name}: righe ignorate perché incomplete o non valide: "
                      + ", ".join(map(str, righe_scartate)) + ".")
    if not trasformazioni:
        raise ErroreConfigurazione([f"{percorso.name}: nessuna regola di trasformazione valida."] + avvisi)
    return trasformazioni, avvisi


def carica_configurazione(percorso_regole: str | Path,
                          percorso_trasformazioni: str | Path) -> Configurazione:
    """Caricamento di entrambi i file; gli errori di tutti e due vengono
    raccolti e segnalati insieme."""
    errori: list[str] = []
    regole = trasformazioni = None
    avvisi: list[str] = []
    try:
        regole = carica_regole(percorso_regole)
    except ErroreConfigurazione as e:
        errori.extend(e.errori)
    try:
        trasformazioni, avvisi = carica_trasformazioni(percorso_trasformazioni)
    except ErroreConfigurazione as e:
        errori.extend(e.errori)
    if errori:
        raise ErroreConfigurazione(errori)
    return Configurazione(regole, trasformazioni, avvisi)


# ---------------------------------------------------------------------------
# Fase 1 - Ricerca della Regola_In
# ---------------------------------------------------------------------------
def trova_regola(sede: str, conf: Configurazione) -> Regola | None:
    """Prima regola (meno jolly, poi ordine del file) di pari lunghezza
    verificata dalla Sede_tecnica già normalizzata."""
    for regola in conf.regole_per_lunghezza.get(len(sede), ()):
        if regola.pattern.fullmatch(sede):
            return regola
    return None


# ---------------------------------------------------------------------------
# Fase 2 - Elaborazione del Codice_Out
# ---------------------------------------------------------------------------
def risolvi_riferimento(token: str, segmenti_sede: list[str]) -> str | None:
    """{Sn} -> segmento n; {Sn.c} -> carattere c; {Sn.c-d} -> caratteri da c a d.
    None se il riferimento non è valido o non esiste nella Sede_tecnica."""
    m = _RE_RIFERIMENTO.fullmatch(token.replace(" ", "").upper())
    if not m:
        return None
    n = int(m.group(1))
    if n < 1 or n > len(segmenti_sede):
        return None
    seg = segmenti_sede[n - 1]
    if m.group(2) is None:
        return seg
    da = int(m.group(2))
    a = int(m.group(3)) if m.group(3) else da
    if da < 1 or a < da or a > len(seg):
        return None
    # NOTA: il carattere prelevato viene accettato qualunque esso sia.
    # Valutare in seguito un controllo aggiuntivo (es. solo cifre).
    return seg[da - 1:a]


def valuta_espressione(espressione: str, segmenti_sede: list[str]) -> str | None:
    """Testo fisso + riferimenti {...}. None se non calcolabile."""
    risultato, i = [], 0
    while i < len(espressione):
        c = espressione[i]
        if c == "{":
            j = espressione.find("}", i + 1)
            if j == -1:
                return None
            parte = risolvi_riferimento(espressione[i + 1:j], segmenti_sede)
            if parte is None:
                return None
            risultato.append(parte)
            i = j + 1
        else:
            risultato.append(c)
            i += 1
    return "".join(risultato)


def contiene_segnaposto(segmento: str) -> bool:
    """Segnaposto irrisolto: jolly "+" o lettere minuscole (es. "nn")."""
    return bool(_RE_SEGNAPOSTO.search(segmento))


def genera_nuova_sede(sede: str, codice_out: str,
                      trasformazioni: dict[int, list[Trasformazione]]) -> tuple[str, bool]:
    """Restituisce (Nuova_Sede_Tecnica, da_verificare).
    In caso di segnaposto irrisolti la stringa è preceduta da PREFISSO_VERIFICA."""
    testo = (codice_out or "").strip()
    if not testo:
        return PREFISSO_VERIFICA + "Codice_Out vuoto", True

    segmenti_sede = sede.split(SEP)
    risultato, da_verificare = [], False

    for posizione, originale in enumerate(testo.split(SEP), start=1):
        for t in trasformazioni.get(posizione, ()):
            # confronto esatto, sensibile a maiuscole e minuscole
            if t.valore_atteso == "" or originale == t.valore_atteso:
                valore = valuta_espressione(t.espressione, segmenti_sede)
                if valore is None:
                    risultato.append(originale)
                    da_verificare = True
                else:
                    risultato.append(valore.upper())
                break
        else:
            if contiene_segnaposto(originale):
                risultato.append(originale)
                da_verificare = True
            else:
                risultato.append(originale.upper())

    nuova = SEP.join(risultato)
    return (PREFISSO_VERIFICA + nuova, True) if da_verificare else (nuova, False)


# ---------------------------------------------------------------------------
# API di alto livello
# ---------------------------------------------------------------------------
def converti(sede_tecnica: Any, conf: Configurazione) -> Risultato:
    sede = normalizza(sede_tecnica)
    if not sede:
        return Risultato(None, None, ESITO_VUOTA)
    regola = trova_regola(sede, conf)
    if regola is None:
        return Risultato(None, None, ESITO_NESSUNA_CORRISPONDENZA)
    nuova, da_verificare = genera_nuova_sede(sede, regola.codice_out, conf.trasformazioni)
    return Risultato(regola.codice_out, nuova,
                     ESITO_DA_VERIFICARE if da_verificare else ESITO_OK)


def elabora_dataframe(df: pd.DataFrame, conf: Configurazione,
                      colonna_sede: str = "Sede_tecnica") -> pd.DataFrame:
    """Restituisce una copia di df con le colonne Codice_Out,
    Nuova_Sede_Tecnica ed Esito. Le Sedi tecniche ripetute vengono
    elaborate una sola volta."""
    if colonna_sede not in df.columns:
        raise KeyError(f"Colonna \"{colonna_sede}\" non presente nel DataFrame.")

    cache: dict[str, Risultato] = {}

    def _converti(valore: Any) -> Risultato:
        chiave = normalizza(valore)
        if chiave not in cache:
            cache[chiave] = converti(chiave, conf)
        return cache[chiave]

    risultati = [_converti(v) for v in df[colonna_sede]]
    out = df.copy()
    out["Codice_Out"] = [r.codice_out for r in risultati]
    out["Nuova_Sede_Tecnica"] = [r.nuova_sede_tecnica for r in risultati]
    out["Esito"] = [r.esito for r in risultati]
    return out


def riepilogo(df_elaborato: pd.DataFrame) -> dict[str, int]:
    """Conteggio delle righe per esito."""
    conteggi = df_elaborato["Esito"].value_counts()
    return {e: int(conteggi.get(e, 0)) for e in
            (ESITO_OK, ESITO_DA_VERIFICARE, ESITO_NESSUNA_CORRISPONDENZA, ESITO_VUOTA)}
