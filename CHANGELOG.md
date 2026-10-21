# Registro delle modifiche

> **Destinatario:** l'utente e Claude Code, per sapere cosa è stato fatto, quando e perché.
> Le voci sono in ordine dalla più recente; tra parentesi il commit git.
> I dettagli delle regole sono nei documenti di specifica:
> - `SPECIFICHE_CONVERSIONE_SEDI.md`: nucleo di conversione;
> - `SPECIFICHE_GUI.md`: interfaccia e flusso;
> - `SPECIFICHE_SAP_SCRIPT.md`: piano e caricamento in SAP, decisioni D1–D22.

---

## 21/10/2026

### No_Wo: esito dell'estrazione sempre visibile (`21052a8`)
- Al termine dell'estrazione compare un messaggio:
  - "nessun Work Order né Notification aperto: si può procedere con lo step SAP script";
  - oppure il conteggio degli aperti da chiudere.
- Sotto la tabella c'è una riga di esito colorata: verde senza aperti, rosso con aperti da chiudere, grigio se l'estrazione non è stata eseguita, arancio se non è più valida.
- L'avviso "da aggiornare" si riferisce alle sole sedi da rimuovere (D2).

### Lunghezza del percorso dei file: 126 caratteri (`0ba0322`)
- Limite del campo file delle transazioni **misurato in SAP** con file di prova: 126 caratteri.
- Nomi dei file accorciati per rientrare nel limite, con la cartella attuale al massimo 122 caratteri:
  - `ZPM4R_FL_DES_MA_LOAD_mod_Step_<n>.xls`;
  - `ZPM4R_FL_DES_MA_LOAD_rim_Step_<n>.xls`;
  - `ZPM4R_CREA_FL_mod_Step_<n>.txt`;
  - `FL_da_creare_Step_<n>.xlsx`.
- I file con i nomi precedenti vengono eliminati alla generazione.

### Caricamento in SAP e file di creazione (`da7edcf`)
- **"Carica in SAP"** nello step SAP script:
  - `ZPM4R_FL_DES_MA_LOAD` (campo `P_FILE`) per modifiche e rimozioni;
  - `ZPM4R_CREA_FL` in modalità modifica (`P_MOD`, campo `FILE`) per le descrizioni.
- SAP resta sulla videata dei risultati e lo step passa a "Caricato - da validare". Se SAP resta sulla videata di selezione con un errore, il file non è stato elaborato.
- **Creazioni:** file `.xlsx` con le colonne `FL` e `Descriptions` per il programma esterno di creazione delle sedi tecniche.
- Caricamento bloccato se il percorso supera il limite del campo (D21).

### Stato del singolo avviso (`84e90b7`)
- Lo stato si legge dal campo `subSCREEN_1:SAPLIQS0:1050/txtRIWO00-STTXT` e non più dall'etichetta `lblRIWO00-STTXT` ("Stato avviso").
- La ricerca per nome tecnico considera solo i campi di input e scarta le etichette.

### Campi del singolo ordine/avviso cercati per nome (`0068647`)
- Con un solo avviso IW29 il campo di stato configurato non esisteva.
- Se l'ID non c'è, stato e sede tecnica vengono cercati nella videata per nome tecnico (`*-STTXT`, `*-TPLNR`).

### "Non sono stati selezionati oggetti" (`a959638`)
- **Anomalia:** con la costante del messaggio scritta con la maiuscola iniziale il confronto falliva, perché il testo veniva convertito in minuscolo. Le estrazioni senza ordini o avvisi finivano quindi in errore.
- **Correzione:** il confronto ignora maiuscole, spazi e punto finale e vale per ogni tipo di messaggio; il risultato vuoto viene riconosciuto correttamente. Verificato in debug sul sistema reale.

## 20/10/2026

### Debug con VS Code (`48be430`)
- Configurazioni in `.vscode/launch.json`, file locale non incluso nel repository.
- I breakpoint funzionano anche nel thread delle estrazioni SAP.

### Step SAP script (`9401e8d`, specifiche `ca85335`, `09c0f87`, `1b86291`)
- Nuovo step **SAP script** tra No_Wo e Check.
- **Piano di caricamento a step** calcolato simulando SAP, con la propagazione delle modifiche ai figli sempre attiva:
  - ciclo Creazione → Modifica → Rimozione;
  - righe transcodificate;
  - figli spostati prima della rimozione del padre;
  - creazioni in più fasi;
  - sedi "trascinate" e dipendenze impossibili segnalate come errori.
- **Rimozione** = spostamento nel cestino `xxA-…` con New Superior uguale al primo livello.
- **Esecuzione:**
  - caricamento e validazione degli step in ordine;
  - dati del progetto bloccati durante il piano;
  - "Interrompi piano" per sbloccarli.
- **Generazione bloccata se:**
  - la riconciliazione è incompleta;
  - No_Wo non è aggiornato o contiene ordini o avvisi aperti;
  - il progetto non è salvato.
- **No_Wo considera solo le sedi da rimuovere:** le sedi modificate mantengono l'ID interno e ordini e avvisi le seguono.
- **Test** resi indipendenti dalle regole in `config/`, con una copia fissa in `tests/dati/`.

## 13/10/2026

### Tema chiaro fisso (`fc970b3`)
- Con Windows in modalità scura il testo bianco era illeggibile sui riquadri e sulle righe colorate.

### Interfaccia grafica PySide6 (`4a12ea8`)
- **Struttura:** barra laterale a passi con lo stato di ogni scheda, progetto `.bessprj` con salvataggio automatico.
- **Tabelle:** ricerca, filtri, ordinamento, colori (testo = origine del dato, sfondo = esito), menu contestuale, esportazione Excel.
- **Check Actual:** decisioni manuali dal menu contestuale e codice scritto a mano con completamento automatico.
- **Check:** pannello delle statistiche.
- **Estrazioni SAP:** finestra di attesa durante l'esecuzione.

### Modello del progetto (`5ac2a3c`)
- Caricamento di New con i controlli bloccanti: colonne, duplicati, impianto unico.
- Tabelle con modifiche manuali conservate: celle modificate, righe rimosse ripristinabili, righe manuali, note.
- Stato delle schede e dipendenze, ricalcolo automatico, salvataggio e riapertura dell'ultimo progetto.

### Check, Check Parent, Riconciliazione (`3875eef`, `ad37108`, `82c81e9`)
- **Riconciliazione:** operazioni Actual → New, identità prima della conversione, conflitti, decisioni manuali.
- **Check Parent:** stato finale dopo il caricamento, controllo di duplicati e parent diretto.
- **Check:** confronto diretto tra SAP e New dopo il caricamento, con statistiche.

### Primo rilascio (`97a5d0f`, `d727b48`)
- Nucleo di conversione (dalla versione VBA) e riga di comando.
- Estrazioni SAP IH06, IW39, IW29 e lettura delle liste esportate negli appunti.
- Specifiche della GUI. Programma ad uso esclusivamente personale.
