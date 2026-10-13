# Conversione Sedi tecniche — Specifiche per l'implementazione in Python

> **Destinatario:** Claude Code.
> Il documento descrive il programma da implementare, contiene il **nucleo di riferimento già verificato** (sezione 8) e la relativa **suite di test** (sezione 9). Il nucleo riproduce fedelmente il comportamento della versione VBA attualmente in uso in Excel.
>
> **Regola fondamentale:** il comportamento del nucleo e i test della sezione 9 costituiscono il contratto del programma. Non modificare la logica di conversione senza averlo concordato con l'utente; qualsiasi modifica concordata deve essere accompagnata dall'aggiornamento dei test.

---

## 1. Obiettivo

Il programma converte un elenco di **Sedi tecniche** (codici come `ITE-OT0B-1E-01-B1-BM`) in **Nuove Sedi tecniche**, in due fasi:

1. **Fase 1 – Riconoscimento:** la Sede tecnica viene confrontata con un elenco di modelli (`Regola_In`), nei quali il carattere `+` è un jolly. Alla prima regola verificata corrisponde un `Codice_Out`.
2. **Fase 2 – Trasformazione:** il `Codice_Out` viene elaborato mediante regole di trasformazione configurabili, che vi ricollocano parti della Sede tecnica originale, producendo la `Nuova_Sede_Tecnica`.

Il programma sostituisce una soluzione VBA in Excel. Nella nuova versione:
- le tabelle delle regole sono **file CSV**;
- l'elenco delle Sedi tecniche è un **DataFrame pandas**.

## 2. Glossario

| Termine | Significato |
|---|---|
| **Sede_tecnica** | Stringa da elaborare, ad esempio `ITE-OT0B-1E-MV-I1-AT`. |
| **Segmento** | Parte di una stringa delimitata dal separatore `-`. I segmenti sono numerati da 1. |
| **Regola_In** | Modello con cui confrontare la Sede_tecnica; `+` = un carattere alfanumerico qualsiasi. |
| **Codice_Out** | Valore associato alla Regola_In nella stessa riga del file delle regole. |
| **Regola di trasformazione** | Terna `Segmento`, `Valore_Atteso`, `Espressione` che stabilisce come sostituire un segmento del Codice_Out. |
| **Nuova_Sede_Tecnica** | Risultato finale, ottenuto applicando le regole di trasformazione al Codice_Out. |

## 3. Dati di input

### 3.1 File `regole.csv`

Colonne obbligatorie: `Regola_In`, `Codice_Out`. Esempio:

```csv
Regola_In;Codice_Out
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
```

### 3.2 File `trasformazioni.csv`

Colonne obbligatorie: `Segmento`, `Valore_Atteso`, `Espressione`. Esempio:

```csv
Segmento;Valore_Atteso;Espressione
1;*;{S1}
2;*;{S2}
3;+E;{S3}
4;++;{S4}
4;nn;0{S5.2}
6;R+;R{S5.2}
```

| Colonna | Significato |
|---|---|
| `Segmento` | Posizione (intero ≥ 1) del segmento del **Codice_Out** a cui si applica la regola. |
| `Valore_Atteso` | Valore che quel segmento deve avere perché la regola si applichi. Confronto **esatto e sensibile a maiuscole/minuscole** (`nn` è un segnaposto, `NN` un valore letterale). `*` o cella vuota = regola sempre valida. |
| `Espressione` | Valore sostitutivo: testo fisso e riferimenti alla **Sede_tecnica**: `{S3}` segmento 3; `{S5.2}` carattere 2 del segmento 5; `{S5.1-2}` caratteri da 1 a 2 del segmento 5. |

### 3.3 Regole di lettura dei CSV (valide per entrambi i file)

- Codifica UTF-8 (anche con BOM), con ripiego su Windows-1252 (CSV salvati da Excel).
- Separatore `;` oppure `,`, rilevato automaticamente dalla riga di intestazione.
- **Tutti i valori sono letti come testo**: `dtype=str`, `keep_default_na=False`. Questo è essenziale: valori come `nn`, `NA`, `01` non devono essere convertiti.
- Intestazioni riconosciute senza distinzione tra maiuscole e minuscole e senza spazi esterni; colonne aggiuntive ignorate; colonne obbligatorie mancanti o duplicate → errore.

### 3.4 DataFrame delle Sedi tecniche

DataFrame pandas con una colonna contenente le Sedi tecniche (nome predefinito `Sede_tecnica`, configurabile). Le altre colonne vengono conservate invariate nell'output.

## 4. Algoritmo

### 4.1 Normalizzazione

La Sede_tecnica e la Regola_In vengono private degli spazi esterni e convertite in maiuscolo. `None`, `NaN` e stringhe vuote → esito `VUOTA`.

### 4.2 Fase 1 – Ricerca della Regola_In

- Il confronto avviene **solo tra stringhe di pari lunghezza**.
- Ogni `+` della Regola_In corrisponde a **un solo carattere alfanumerico** `[A-Z0-9]` (mai `-` né altri simboli). Tutti gli altri caratteri sono letterali.
- Il confronto riguarda l'intera stringa (`fullmatch`), non una sua parte.
- Con più regole verificate prevale quella con **meno jolly**; a parità, quella che compare **prima nel file**.
- Nessuna regola verificata → esito `NESSUNA_CORRISPONDENZA` (equivalente di `#N/D` in Excel).

### 4.3 Fase 2 – Generazione della Nuova_Sede_Tecnica

1. Sede_tecnica e Codice_Out vengono scomposti in segmenti con il separatore `-`. Le due stringhe **non** hanno necessariamente lo stesso numero di segmenti.
2. Per ogni segmento del Codice_Out (posizione *k*) si applica la **prima** regola di trasformazione, nell'ordine del file, con `Segmento = k` e `Valore_Atteso` uguale al segmento (o `*`/vuoto).
3. Le regole leggono sempre la Sede_tecnica e il Codice_Out **originali**, mai i risultati parziali.
4. Il valore calcolato viene convertito in maiuscolo.
5. I segmenti senza regola applicabile restano invariati (in maiuscolo).
6. Il risultato è **DA VERIFICARE** quando:
   - un segmento senza regola applicabile contiene `+` o lettere minuscole (segnaposto irrisolto, come `nn`);
   - un'espressione non è calcolabile (segmento o carattere inesistente nella Sede_tecnica, riferimento malformato, `{` non chiusa). In questo caso il segmento resta invariato.

   La Nuova_Sede_Tecnica è allora preceduta da `DA VERIFICARE: ` e l'esito è `DA_VERIFICARE`.

### 4.4 Esempi di riferimento

| Sede_tecnica | Regola_In | Codice_Out | Nuova_Sede_Tecnica |
|---|---|---|---|
| `ITE-OT0B-1E-MV-I1-AT` | `++E-++++-+E-MV-I+-AT` | `++E-++++-+E-nn-MV-AT` | `ITE-OT0B-1E-01-MV-AT` |
| `ITE-OT0B-1E-01-B1-BS` | `++E-++++-+E-++-B1-BS` | `++E-++++-+E-++-C1-BS` | `ITE-OT0B-1E-01-C1-BS` |
| env | `++E-++++-+E-++-B+-BM` | `++E-++++-+E-++-C1-R+` | `ITE-OT0B-1E-01-C1-R1` |
| `ITE-OT0B-1E-MV-I1` | `++E-++++-+E-MV-I+` | `++E-++++-+E-nn-MV-RM` | `ITE-OT0B-1E-01-MV-RM` |
| `ITE-OT0B-0E-SA` | `++E-++++-0E-SA` | `++E-++++-1A-S1` | `ITE-OT0B-1A-S1` |
| `ITE-OT0B-00` | — | — | *nessuna corrispondenza* |

## 5. Gestione degli errori

- **Errori bloccanti** (eccezione `ErroreConfigurazione`, con l'elenco completo dei problemi di entrambi i file): file mancante o vuoto; intestazione obbligatoria mancante o duplicata; nessuna regola valida in uno dei due file.
- **Avvisi non bloccanti** (`Configurazione.avvisi`): righe di `trasformazioni.csv` ignorate perché incomplete o non valide (Segmento non intero o < 1, Espressione vuota), con il numero di riga del file. Le righe completamente vuote vengono ignorate senza avviso.
- I messaggi sono in italiano e devono essere mostrati all'utente in modo leggibile (non come traceback).

## 6. Output

`elabora_dataframe` restituisce una **copia** del DataFrame di input con tre colonne aggiunte:

| Colonna | Contenuto |
|---|---|
| `Codice_Out` | Codice_Out della regola verificata, tal quale; `None` se nessuna corrispondenza. |
| `Nuova_Sede_Tecnica` | Risultato della trasformazione (eventualmente con prefisso `DA VERIFICARE: `); `None` se nessuna corrispondenza. |
| `Esito` | `OK`, `DA_VERIFICARE`, `NESSUNA_CORRISPONDENZA`, `VUOTA`. |

`riepilogo` restituisce il conteggio delle righe per esito.

## 7. Architettura proposta

```
conversione_sedi/
├── pyproject.toml
├── README.md
├── conversione_sedi/
│   ├── __init__.py
│   ├── nucleo.py        # sezione 8 — da copiare così com'è
│   └── cli.py           # da implementare (sezione 10)
├── config/
│   ├── regole.csv
│   └── trasformazioni.csv
└── tests/
    └── test_nucleo.py   # sezione 9 — da copiare così com'è
```

Requisiti: Python ≥ 3.10, pandas ≥ 2.0, pytest per i test.

## 8. Nucleo di riferimento — `conversione_sedi/nucleo.py`

> Codice già verificato (23 test superati; 50.000 righe elaborate in circa 0,4 s). Da copiare **senza modifiche**.

```python
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
```

## 9. Test di riferimento — `tests/test_nucleo.py`

> Da copiare **senza modifiche**. Tutti i test devono essere superati prima e dopo qualsiasi sviluppo successivo.

```python
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
```

## 10. Istruzioni operative per Claude Code

1. **Prima di scrivere codice**, porre all'utente le domande della sezione 11 ancora senza risposta.
2. Creare la struttura della sezione 7, copiare `nucleo.py` e `test_nucleo.py` dalle sezioni 8 e 9, ed eseguire `pytest`: tutti i test devono passare.
3. Creare `config/regole.csv` e `config/trasformazioni.csv` con i contenuti della sezione 3 (oppure con i file forniti dall'utente).
4. Implementare il livello di ingresso/uscita (`cli.py` o altro, secondo le risposte alla sezione 11):
   - caricamento della configurazione con `carica_configurazione`;
   - visualizzazione chiara di errori (`ErroreConfigurazione.errori`) e avvisi (`Configurazione.avvisi`);
   - lettura delle Sedi tecniche nel DataFrame, elaborazione con `elabora_dataframe`, salvataggio dell'output e stampa del `riepilogo`.
5. Aggiungere test per il nuovo codice (lettura/scrittura file, gestione degli errori), senza alterare quelli esistenti.
6. Redigere un `README.md` in italiano: installazione, formato dei CSV, sintassi delle espressioni, esempi d'uso.

**Vincoli:**
- La logica di conversione resta interamente in `nucleo.py`; gli altri moduli si occupano solo di ingresso, uscita e interfaccia.
- Mantenere `dtype=str` e `keep_default_na=False` in **ogni** lettura di dati (anche del file delle Sedi tecniche), per evitare conversioni indesiderate.
- Se l'output viene scritto in Excel, le colonne di testo devono restare testo (valori come `++E-...` o `01` non vanno interpretati come formule o numeri).
- Codice, commenti, messaggi e documentazione in italiano, coerenti con la terminologia del glossario.

## 11. Decisioni da confermare con l'utente

Il nucleo adotta già le scelte della versione VBA. Restano da definire i seguenti aspetti del livello di ingresso/uscita:

1. **Origine delle Sedi tecniche:** file Excel, CSV, query a un database o DataFrame già disponibile in un altro programma? Qual è il nome della colonna?
2. **Destinazione dell'output:** nuovo file Excel, CSV, oppure solo il DataFrame restituito al chiamante?
3. **Modalità d'uso:** riga di comando, libreria importata da altri script, notebook Jupyter?
4. **Percorso dei CSV delle regole:** fisso (cartella `config/`) o indicato a ogni esecuzione?
5. **Prefisso `DA VERIFICARE: `:** mantenerlo nella Nuova_Sede_Tecnica (come in VBA) o affidarsi alla sola colonna `Esito`, lasciando il codice parziale senza prefisso?

## 12. Possibili evoluzioni (non richieste ora)

- Controllo che il carattere prelevato dalle espressioni `{Sn.c}` sia una cifra, con esito `DA_VERIFICARE` in caso contrario (punto già annotato nel codice).
- Avviso per `Regola_In` duplicate o mai utilizzate nell'elaborazione.
- Colonna diagnostica con la `Regola_In` verificata.
