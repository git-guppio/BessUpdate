# Conversione Sedi tecniche

Converte un elenco di **Sedi tecniche** (es. `ITE-OT0B-1E-01-B1-BM`) in **Nuove Sedi tecniche**
(es. `ITE-OT0B-1E-01-C1-R1`), applicando regole definite in due file CSV.
Sostituisce la versione VBA in Excel (modulo `modNuovoCodice`) e ne riproduce fedelmente il comportamento.

La conversione avviene in due fasi:

1. **Riconoscimento:** la Sede tecnica viene confrontata con i modelli `Regola_In` di `regole.csv`;
   alla regola verificata corrisponde un `Codice_Out`.
2. **Trasformazione:** il `Codice_Out` viene elaborato con le regole di `trasformazioni.csv`,
   che vi ricollocano parti della Sede tecnica originale, producendo la `Nuova_Sede_Tecnica`.

## Installazione

Requisiti: Python ≥ 3.10.

```bash
cd conversione_sedi
pip install -e .            # installa pandas e openpyxl
pip install -e .[test]      # in più, pytest per eseguire i test
```

L'installazione in modalità modificabile (`-e`) mantiene il collegamento alla cartella `config/`,
usata come percorso predefinito dei file delle regole.

Per verificare l'installazione:

```bash
python -m pytest
```

## Uso dalla riga di comando

```bash
python -m conversione_sedi sedi.xlsx
```

(dopo l'installazione è disponibile anche il comando `conversione-sedi`).

Viene creato `sedi_convertito.xlsx` nella stessa cartella, con tutte le colonne dell'input più
`Codice_Out`, `Nuova_Sede_Tecnica` ed `Esito`, e viene stampato il riepilogo:

```
Elaborate 3 righe.
  OK                      2
  DA_VERIFICARE           0
  NESSUNA_CORRISPONDENZA  1
  VUOTA                   0
Output salvato in: ...\sedi_convertito.xlsx
```

| Opzione | Significato |
|---|---|
| `input` | File delle Sedi tecniche: `.xlsx`, `.xlsm` o `.csv`. |
| `-o`, `--output` | File di output `.xlsx` o `.csv`. Predefinito: `<input>_convertito.<estensione>` (i `.xlsm` diventano `.xlsx`). |
| `-c`, `--colonna` | Nome della colonna delle Sedi tecniche. Predefinito: `Sede tecnica` oppure `Sede_tecnica`. |
| `-f`, `--foglio` | Nome del foglio Excel da leggere. Predefinito: il primo. |
| `--regole` | File delle regole. Predefinito: `config/regole.csv`. |
| `--trasformazioni` | File delle trasformazioni. Predefinito: `config/trasformazioni.csv`. |

Esempi:

```bash
# CSV in ingresso, output in Excel, colonna con nome diverso
python -m conversione_sedi estrazione.csv -o risultato.xlsx --colonna "FL"

# foglio specifico e regole di prova
python -m conversione_sedi sedi.xlsx -f "Elenco" --regole prove/regole.csv --trasformazioni prove/trasf.csv
```

Il nome della colonna è riconosciuto senza distinzione tra maiuscole e minuscole, ignorando gli spazi
esterni e la differenza tra spazio e `_`.

In caso di errore viene mostrato un messaggio leggibile e il programma termina con codice 1;
gli avvisi (es. righe ignorate in `trasformazioni.csv`) vengono mostrati senza interrompere l'elaborazione.

## Uso come libreria

```python
from conversione_sedi import converti_file, carica_configurazione, elabora, ErroreConfigurazione, ErroreDati

# da file a file
esito = converti_file("sedi.xlsx", "risultato.xlsx")
print(esito.riepilogo, esito.avvisi)

# da un DataFrame già disponibile (es. da un'interfaccia grafica)
conf = carica_configurazione("config/regole.csv", "config/trasformazioni.csv")
esito = elabora(df, conf)                 # colonna "Sede tecnica" o "Sede_tecnica"
df_out = esito.dati
```

Funzioni principali:

| Funzione | Modulo | Descrizione |
|---|---|---|
| `carica_configurazione(regole, trasformazioni)` | `nucleo` | Legge e verifica i due CSV; solleva `ErroreConfigurazione`. |
| `elabora_dataframe(df, conf, colonna_sede)` | `nucleo` | Restituisce una copia di `df` con le tre colonne di output. |
| `riepilogo(df_elaborato)` | `nucleo` | Conteggio delle righe per esito. |
| `leggi_sedi(percorso, foglio=None)` | `ingresso_uscita` | Legge un file Excel o CSV come testo puro. |
| `elabora(df, conf, colonna=None)` | `ingresso_uscita` | Individua la colonna, elabora e restituisce `EsitoElaborazione`. |
| `scrivi_output(df, percorso)` | `ingresso_uscita` | Salva in `.xlsx` (celle in formato testo) o `.csv`. |
| `converti_file(input, output=None, ...)` | `ingresso_uscita` | Tutte le operazioni precedenti in sequenza. |

## Formato dei file CSV delle regole

Regole di lettura comuni ai due file:

- codifica UTF-8 (anche con BOM) oppure Windows-1252 (CSV salvati da Excel);
- separatore `;` oppure `,`, rilevato automaticamente dalla riga di intestazione;
- tutti i valori sono letti come testo (`nn`, `NA`, `01` restano invariati);
- intestazioni riconosciute senza distinzione tra maiuscole e minuscole; colonne aggiuntive ignorate.

### `regole.csv`

```csv
Regola_In;Codice_Out
++E-++++-+E-++-B+-BM;++E-++++-+E-++-C1-R+
++E-++++-0E-SA;++E-++++-1A-S1
++E-++++-+E-MV-I+;++E-++++-+E-nn-MV-RM
```

- Nella `Regola_In` ogni `+` corrisponde a **un solo carattere alfanumerico** (`A-Z`, `0-9`, mai `-`);
  tutti gli altri caratteri devono coincidere. Il confronto non distingue maiuscole e minuscole.
- La Sede tecnica deve avere la **stessa lunghezza** della Regola_In.
- Se più regole sono verificate prevale quella con **meno `+`**; a parità, quella che compare **prima** nel file.

### `trasformazioni.csv`

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
| `Segmento` | Posizione (da 1) del segmento del **Codice_Out** a cui si applica la regola. I segmenti sono le parti separate da `-`. |
| `Valore_Atteso` | Valore che il segmento deve avere perché la regola si applichi. Confronto **esatto, sensibile alle maiuscole** (`nn` ≠ `NN`). `*` o vuoto = sempre. |
| `Espressione` | Valore che sostituisce il segmento. |

Per ogni segmento del Codice_Out si applica la **prima** regola (nell'ordine del file) con il segmento
e il valore atteso corrispondenti. I segmenti senza regola restano invariati.

### Sintassi delle espressioni

Le espressioni contengono testo fisso e riferimenti tra parentesi graffe alla **Sede tecnica originale**:

| Riferimento | Significato | Esempio su `ITE-OT0B-1E-MV-I1-AT` |
|---|---|---|
| `{S3}` | segmento 3 | `1E` |
| `{S5.2}` | carattere 2 del segmento 5 | `1` |
| `{S2.1-2}` | caratteri da 1 a 2 del segmento 2 | `OT` |
| `0{S5.2}` | testo fisso + riferimento | `01` |

Il risultato viene convertito in maiuscolo.

## Esiti

| Esito | Significato |
|---|---|
| `OK` | Conversione completata. |
| `DA_VERIFICARE` | Restano segnaposto irrisolti (`+` o lettere minuscole, es. `nn`) oppure un'espressione non è calcolabile (riferimento inesistente o malformato). La Nuova_Sede_Tecnica è preceduta da `DA VERIFICARE: `. |
| `NESSUNA_CORRISPONDENZA` | Nessuna Regola_In verificata (equivale a `#N/D` in Excel). `Codice_Out` e `Nuova_Sede_Tecnica` restano vuoti. |
| `VUOTA` | Cella della Sede tecnica vuota. |

Esempi:

| Sede tecnica | Codice_Out | Nuova_Sede_Tecnica | Esito |
|---|---|---|---|
| `ITE-OT0B-1E-MV-I1-AT` | `++E-++++-+E-nn-MV-AT` | `ITE-OT0B-1E-01-MV-AT` | OK |
| `ITE-OT0B-1E-01-B1-BM` | `++E-++++-+E-++-C1-R+` | `ITE-OT0B-1E-01-C1-R1` | OK |
| `ITE-OT0B-0E-SA` | `++E-++++-1A-S1` | `ITE-OT0B-1A-S1` | OK |
| `ITE-OT0B-00` | | | NESSUNA_CORRISPONDENZA |

## File di output

- **Excel (`.xlsx`):** foglio "Sedi tecniche", tutte le celle in formato Testo, così che valori come
  `++E-...` o `01` non vengano interpretati come formule o numeri; intestazione bloccata e filtro attivo.
- **CSV:** separatore `;`, codifica UTF-8 con BOM (apribile direttamente in Excel).

## Struttura del progetto

```
conversione_sedi/
├── pyproject.toml
├── README.md
├── conversione_sedi/
│   ├── __init__.py
│   ├── __main__.py          # python -m conversione_sedi
│   ├── nucleo.py            # logica di conversione (riferimento verificato, non modificare)
│   ├── ingresso_uscita.py   # lettura/scrittura file ed elaborazione completa
│   └── cli.py               # riga di comando
├── config/
│   ├── regole.csv
│   └── trasformazioni.csv
└── tests/
    ├── test_nucleo.py           # test di riferimento (non modificare)
    └── test_ingresso_uscita.py
```

Tutta la logica di conversione risiede in `nucleo.py`; gli altri moduli si occupano solo di ingresso,
uscita e interfaccia. Qualsiasi modifica alla logica va concordata e accompagnata dall'aggiornamento dei test.
