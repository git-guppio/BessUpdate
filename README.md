# BESS Update

Strumento per **allineare le sedi tecniche SAP di un impianto BESS a una nuova codifica**.

Il programma confronta le sedi tecniche presenti in SAP con la nuova codifica proposta. Stabilisce per ogni sede se va mantenuta, rinominata, rimossa o creata, verifica la gerarchia risultante e prepara i file di caricamento in SAP nell'ordine corretto. Dopo il caricamento controlla che SAP corrisponda esattamente alla nuova codifica.

> Uso personale: script Python avviato sul PC dell'utente, con SAP GUI e accesso in lingua italiana.

---

## Come funziona

L'interfaccia guida il lavoro in nove passi. Ogni passo si sblocca quando i precedenti sono completi.

| # | Passo | Cosa fa |
|---|---|---|
| 1 | **New** | Carica da Excel la nuova codifica (sede tecnica e descrizione), controllando impianto unico e duplicati. |
| 2 | **Actual** | Estrae da SAP le sedi tecniche dell'impianto (IH06). |
| 3 | **FL da creare** | Converte le sedi attuali con le regole di conversione configurabili (`config/regole.csv`). |
| 4 | **Check New** | Per ogni sede della nuova codifica: esiste già, nasce da una modifica, va creata. |
| 5 | **Check Actual** | Per ogni sede in SAP: invariata, da modificare, da rimuovere. Qui si risolvono a mano i casi dubbi e i conflitti. |
| 6 | **Check Parent** | Verifica la gerarchia della struttura finale: duplicati e parent mancanti. |
| 7 | **No_Wo** | Cerca ordini (IW39) e avvisi (IW29) aperti sulle sedi da rimuovere, che vanno chiusi prima di procedere. |
| 8 | **SAP script** | Calcola il piano di caricamento a step, genera i file e li carica in SAP uno alla volta, con la validazione di ogni esito. |
| 9 | **Check** | Dopo il caricamento confronta SAP con la nuova codifica e mostra le statistiche di allineamento. |

### Il piano di caricamento

In SAP la modifica di una sede tecnica si propaga sempre a tutto il suo sottoalbero. Per questo il programma **simula SAP passo per passo** e costruisce gli step nell'ordine corretto:
- crea prima i parent mancanti;
- rinomina le sedi; i figli raggiunti per propagazione non richiedono righe proprie, gli altri usano il codice che avranno in quel momento;
- sposta fuori i figli da conservare prima di rimuovere il padre;
- segnala i casi impossibili invece di produrre file che fallirebbero.

| Step | File | Caricamento |
|---|---|---|
| Creazione | `FL_da_creare_Step_<n>.xlsx` | Programma esterno di creazione delle sedi tecniche |
| Modifica | `ZPM4R_FL_DES_MA_LOAD_mod_Step_<n>.xls` | Transazione `ZPM4R_FL_DES_MA_LOAD` |
| Rimozione | `ZPM4R_FL_DES_MA_LOAD_rim_Step_<n>.xls` | Transazione `ZPM4R_FL_DES_MA_LOAD`. La sede viene spostata nella struttura cestino `xxA-…` |
| Modifica descrizione | `ZPM4R_CREA_FL_mod_Step_<n>.txt` | Transazione `ZPM4R_CREA_FL` in modalità modifica |

---

## Requisiti

- Windows, **Python ≥ 3.10**.
- **SAP GUI** con scripting abilitato sul server e sul client, sessione aperta con accesso in **italiano**.
- Layout utente SAP: `FL_BESS_MIG` (IH06), `OdM_BESS_MIG` (IW39), `AdM_BESS_MIG` (IW29).

## Installazione

```powershell
git clone <url-del-repository> BESS_Update
cd BESS_Update
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".\conversione_sedi[test]"
```

Vengono installate pandas, openpyxl, xlwt, pywin32, PySide6 e, per i test, pytest e xlrd.

## Avvio

```powershell
.venv\Scripts\python.exe -m conversione_sedi.gui
```

Il lavoro viene salvato automaticamente in un file di progetto `.bessprj`, riaperto al successivo avvio. I file di caricamento vengono creati nella cartella `SAP_<impianto>` accanto al file di progetto.

> Il campo file delle transazioni SAP accetta al massimo **126 caratteri**: conviene tenere il progetto in una cartella con un percorso breve.

È disponibile anche una riga di comando per la sola conversione di un elenco di sedi:

```powershell
.venv\Scripts\python.exe -m conversione_sedi sedi.xlsx
```

## Test

```powershell
cd conversione_sedi
..\.venv\Scripts\python.exe -m pytest
```

I test non richiedono SAP: le transazioni sono simulate. Usano una copia fissa delle regole di conversione (`tests/dati/`), quindi le regole in `config/` si possono modificare liberamente.

---

## Struttura del repository

```
BESS_Update/
├── README.md                        # questo file
├── CHANGELOG.md                     # registro delle modifiche
├── SPECIFICHE_CONVERSIONE_SEDI.md   # nucleo di conversione (regole e algoritmo)
├── SPECIFICHE_GUI.md                # interfaccia, passi e regole di ciascuna scheda
├── SPECIFICHE_SAP_SCRIPT.md         # piano e caricamento in SAP (decisioni D1–D22)
├── Specifiche generali.md           # richiesta iniziale
├── template_SAP/                    # template dei file SAP (CC04, ZPM4R_CREA_FL)
├── sap_connection.py, sap_trasactions.py   # registrazioni SAP originali (riferimento)
└── conversione_sedi/                # pacchetto Python
    ├── README.md                    # manuale d'uso dettagliato
    ├── config/                      # regole di conversione e intestazioni dei template
    ├── conversione_sedi/            # codice (logica, SAP, interfaccia in gui/)
    └── tests/                       # test automatici
```

## Documentazione

- **[conversione_sedi/README.md](conversione_sedi/README.md):** manuale d'uso. Formato delle regole di conversione, sintassi delle espressioni, colori, riga di comando, uso come libreria.
- **[SPECIFICHE_GUI.md](SPECIFICHE_GUI.md):** comportamento di ogni scheda e decisioni di progetto.
- **[SPECIFICHE_SAP_SCRIPT.md](SPECIFICHE_SAP_SCRIPT.md):** algoritmo del piano di caricamento e decisioni sul caricamento in SAP.
- **[SPECIFICHE_CONVERSIONE_SEDI.md](SPECIFICHE_CONVERSIONE_SEDI.md):** nucleo di conversione, equivalente alla versione VBA originale.
- **[CHANGELOG.md](CHANGELOG.md):** cronologia delle implementazioni.
