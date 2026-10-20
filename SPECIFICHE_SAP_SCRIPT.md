# Step "SAP script" — richiesta, analisi e domande aperte

> **Destinatario:** Claude Code e l'utente, per riprendere il lavoro.
> **Stato:** tutte le domande hanno risposta (sezione 4); algoritmo definito (sezione 5). Implementazione in corso.
> **Data:** 20/10/2026. Ultimo commit al momento della stesura: `ca85335`.
> **Fonti:** richiesta del 19/10 in chat; `specifiche_integrative.md` del 20/10, integrato qui sotto.

---

## 1. Richiesta dell'utente (19/10/2026)

**Nuovo step "SAP script"** nella barra laterale, dopo **7. No_Wo** e prima di **8. Check**:
- crea i file di caricamento in SAP;
- avvia gli script SAP che leggono quei file.

**Pulsanti:**
- un pulsante crea i file per modifica, rimozione e creazione dei dati in SAP;
- al termine della creazione si attiva un pulsante di caricamento **solo per i file effettivamente creati**. Il pulsante avvia gli script SAP che leggono quei file; gli script verranno specificati in seguito;
- per ogni file creato viene indicato quante sedi tecniche saranno rimosse, modificate, rinominate o create.

**File da creare**, in base alla colonna **"Operazione"** della scheda Check Actual (e, per le creazioni, alla colonna "Stato" di Check New):

| Operazione | File | Formato | Contenuto |
|---|---|---|---|
| Modifica descrizione | `ZPM4R_CREA_FL_modifica_upload.txt` | Testo separato da tabulazioni, intestazioni come `template_SAP/ZPM4R_CREA_FL_Template.txt`. Transazione `ZPM4R_CREA_FL` in modalità modifica | Valorizzati solo: `TPLNR` = Sede tecnica; `PLTXT` = nuova descrizione; `COUNTRY` = primi due caratteri del primo livello (`USE-US64-1A` → `US`) |
| Da rimuovere | `CC04_rimuovere_upload.xls` | Excel `.xls`, intestazioni come `template_SAP/CC04_Template.xls` | Vedi sotto |
| Modifica | `CC04_modificare_upload.xls` | Excel `.xls`, intestazioni come `template_SAP/CC04_Template.xls` | Vedi sotto |
| Da creare | `ZPM4R_CREA_FL_crea_upload.txt` | Testo separato da tabulazioni, intestazioni come il template ZPM4R | **Rimandato**: il contenuto verrà definito in seguito. Le creazioni sono divise in **due fasi**: vedi 3.2 e 4 |

**Rimozione (CC04):** si sposta la sede in una nuova struttura, sostituendo il **terzo carattere del primo livello** con `A`.

| Colonna | Valore | Esempio |
|---|---|---|
| Functional Location | Sede tecnica | `USE-US64-1E-02-B4` |
| New Code | Sede con il 3° carattere del 1° livello sostituito da `A` | `USA-US64-1E-02-B4` |
| Description (if required) | Descrizione | `Battery Bank 3 of Container 03` |
| New Superior | **Solo il primo livello** modificato (confermato, vedi 3.3) | `USA` |

**Modifica (CC04):** si assegna alla sede un altro codice.

| Colonna | Valore | Esempio |
|---|---|---|
| Functional Location | Sede tecnica | `USE-US64-1A-S1-TR` |
| New Code | Nuova sede tecnica | `USE-US64-1A-S1-T1` |
| Description (if required) | Nuova descrizione | `Ausiliary Transformer` |
| New Superior | Parent del New Code | `USE-US64-1A-S1` |

## 2. Cosa risulta dai template

- **`template_SAP/ZPM4R_CREA_FL_Template.txt`**: una sola riga di intestazione, **70 colonne** separate da tabulazione, senza fine riga.
  - Contiene `TPLNR`, `PLTXT`, `COUNTRY` e molte altre colonne (`TPLKZ`, `FLTYP`, `EQART`, `SWERK`, `IWERK`, `TPLMA`, `BUKRS`, ...).
  - La colonna `TEL_NUMBER_OLD ` ha uno **spazio finale**: va riprodotta identica.
- **`template_SAP/CC04_Template.xls`**: vero formato Excel 97-2003 (BIFF), un foglio `Foglio1`, una riga di intestazione.
  - Colonne: `Functional Location`, `New Code`, `Description (if required)`, `New Superior `.
  - `New Superior ` ha uno **spazio finale**.
- Nel `.venv` non ci sono librerie per i file `.xls`. Servirà `xlwt` per scriverli.

## 3. Informazioni fornite dall'utente (20/10/2026)

### 3.1 Etichetta e ID interno; ordini e avvisi da chiudere
- Ogni sede tecnica ha un **ID interno SAP** e un'**etichetta** visibile, cioè il codice.
- **Modificare l'etichetta** (CC04) non cambia l'ID: avvisi e ordini restano collegati alla sede e assumono automaticamente la nuova etichetta. Le sedi solo modificate **non** richiedono la chiusura di ordini e avvisi.
- **Eliminare e ricreare** una sede genera un nuovo ID: ordini e avvisi non vengono ereditati e vanno chiusi prima.
- Ordini e avvisi da chiudere riguardano **solo le sedi da eliminare**.

**Conseguenza sul programma:** No_Wo (step 7) deve considerare **solo le sedi "Da rimuovere"**. Oggi `Progetto.sedi_per_no_wo()` (`progetto.py`) cerca anche le sedi "Modifica": va corretto. Vedi anche la domanda 5.1.

### 3.2 Sequenza di creazione e modifica
Una sede si può creare solo se il suo **genitore esiste già**.
- **Creazione, fase 1:** sedi mancanti il cui genitore esiste già nella struttura attuale.
- **Creazione, fase 2:** sedi il cui genitore sarà disponibile solo **dopo una modifica** (ridenominazione). Vanno nella fase successiva. La valutazione è fatta sede per sede.
- **Esempio:** una sede di 5° livello non può essere creata finché non esiste il genitore di 4° livello, che potrebbe essere creato oppure ottenuto rinominando una sede esistente.

### 3.3 New Superior delle rimozioni
- Per le rimozioni il New Superior è **sempre il primo livello**: i primi due caratteri più `A` (es. `USA`).
- È un livello **sicuramente esistente**. Indicare il parent completo farebbe fallire la riga se manca un parent intermedio.
- **La domanda precedente 3.3 è chiusa:** sì, è voluto, e la radice esiste.

### 3.4 Propagazione ai figli e transcodifica
- La CC04 massiva **consente** di propagare la modifica del codice ai figli.
- La propagazione non elimina la necessità di ordinare correttamente creazioni, modifiche ed eliminazioni. Una modifica può trasformare i codici dei figli, che non sarebbero più riconoscibili nella lista originale.
- Le eliminazioni vanno collocate tenendo conto delle modifiche: se un codice cambia prima della sua eliminazione, bisognerebbe **transcodificarlo**, cioè ricalcolare il codice che avrà in quel momento. La sequenza deve preservare i codici fino al momento opportuno.

### 3.5 Attività richieste
| # | Attività | Descrizione |
|---|---|---|
| 1 | Sequenza di migrazione | Creare prima le sedi con genitore già esistente e rinviare allo step successivo quelle senza genitore, verificando la gerarchia per ogni sede. |
| 2 | Ordine di esecuzione | Creare prima le sedi necessarie alla gerarchia, prima delle modifiche o eliminazioni che potrebbero cambiarne i codici. |

## 4. Decisioni (risposte del 20/10/2026)

| # | Tema | Decisione |
|---|---|---|
| D1 | Rimozione | "Da rimuovere" = **spostamento** nella struttura cestino `xxA-…` (3° carattere del 1° livello = `A`). Ordini e avvisi seguono la sede. |
| D2 | Ordini e avvisi | Vanno chiusi **esattamente** per le sedi "Da rimuovere". No_Wo considera solo quelle. |
| D3 | Elimina e ricrea | Il caso "elimina e ricrea con lo stesso codice" **non esiste**. |
| D4 | Blocco No_Wo | Se l'ultima estrazione No_Wo trova ordini o avvisi aperti su sedi da rimuovere, **la struttura non si può modificare**: lo step SAP script è bloccato, con un messaggio esplicito. La verifica si supera solo con una nuova estrazione che non trovi nulla; le righe tolte a mano da No_Wo non contano. |
| D5 | Propagazione | **Non si può disattivare**: ogni modifica o rimozione di una sede si propaga a tutto il suo sottoalbero. |
| D6 | Nomi dei file | Suffisso `_Step_<n>`, dove n è la posizione del file nel piano. Esempio: `CC04_modificare_upload_Step_2.xls`. Il suffisso si usa sempre, anche quando un tipo di file compare una volta sola. |
| D7 | Ordine delle righe | All'interno di un file SAP elabora le righe **in ordine**: una riga può contare sul risultato delle precedenti. |
| D8 | Validazione | Dopo ogni caricamento l'utente legge i messaggi SAP e registra **"Esito OK"**, che sblocca lo step successivo, oppure **"Esito con errori"**, che ferma il piano: si corregge in SAP e si ricarica, oppure si interrompe il piano. |
| D9 | Sedi trascinate | Una sede che deve restare com'è (Invariata, Modifica descrizione, Mantenuta) sotto un padre che viene rinominato o rimosso: **errore bloccante**. La sede viene elencata con il motivo e va corretta la decisione. |
| D10 | Piano avviato | Dalla prima validazione il **piano è bloccato**: i dati del progetto non si possono modificare. Per cambiarli si sceglie **"Interrompi piano"** (con conferma), poi si riestrae Actual da SAP, che riflette i caricamenti fatti, e si genera un nuovo piano. |
| D11 | Pulsante | La creazione dei file avviene nello step **SAP script**. |
| D12 | Sedi da creare | Sono quelle con Stato "Da creare" in **Check New**. Il contenuto del file è rimandato. |
| D13 | Dati cambiati | Dati cambiati dopo la generazione e prima dell'avvio del piano: lo step passa a ⚠ "Da aggiornare" e i caricamenti restano disattivati finché i file non vengono rigenerati. |
| D14 | Primo livello con `A` | Se il terzo carattere del primo livello è già `A` (non dovrebbe accadere, perché `A` identifica solo il cestino): errore. |
| D15 | Cestino occupato | Se il codice `xxA-…` esiste già in SAP, lo segnala SAP al caricamento e l'utente ne prende atto. |
| D16 | Dettagli tecnici | Confermate tutte le proposte: cartella `SAP_<impianto>` accanto al `.bessprj`, sovrascritta a ogni generazione; `.txt` in Windows-1252 senza BOM, righe CRLF, intestazione identica al template; `.xls` Excel 97-2003 con `xlwt`, foglio `Foglio1`; avviso per descrizioni oltre 40 caratteri; COUNTRY = primi due caratteri del primo livello; intestazioni copiate in `config/`. |

## 5. Piano di caricamento: algoritmo

Il programma simula SAP passo per passo sulla struttura attuale (Actual) e costruisce un **piano di step**. Ogni step è un file di un solo tipo.

### 5.1 Modello
- **Sedi di Actual** con il loro sottoalbero (padre = sede senza l'ultimo segmento). La radice di livello 1 e la radice del cestino (`xxA`) si considerano esistenti.
- **Destinazione di ogni sede:**
  - *fissa*: Esclusa, Invariata, Modifica descrizione, Mantenuta;
  - *spostamento* verso la Nuova sede tecnica: Modifica;
  - *cestino*: Da rimuovere.
- **Sedi da creare:** Stato "Da creare" in Check New.

### 5.2 Operazioni e condizioni
| Operazione | Condizioni perché sia eseguibile | Effetto (con propagazione) |
|---|---|---|
| **Creazione** di `T` | `T` libero; il padre di `T` esiste ed è già nella sua posizione finale | Nuova sede `T` |
| **Modifica** `S` → `T` | `T` libero; il padre di `T` esiste, è nella posizione finale e non sta dentro il sottoalbero di `S`; i nuovi codici dei discendenti sono liberi | `S` e tutto il sottoalbero cambiano prefisso. I discendenti che raggiungono così la loro destinazione sono completati **senza riga** ("per propagazione"). Quelli con un'altra destinazione verranno spostati con il codice **transcodificato** |
| **Rimozione** di `S` | Nel sottoalbero di `S` restano solo sedi da rimuovere: quelle da spostare altrove devono essere già uscite. Si rimuove solo la sede **più alta**: i discendenti la seguono per propagazione | `S` → `xxA-…` sotto la radice del cestino, insieme al sottoalbero |
| **Modifica descrizione** | Nessuna | Ultimo step: il codice è quello finale |

**Errori bloccanti verificati prima della simulazione:**
- D9: una sede *fissa* ha un antenato da modificare o rimuovere;
- D14: il primo livello ha già `A` come terzo carattere.

### 5.3 Costruzione degli step
Si ripete il ciclo **Creazione → Modifica → Rimozione** finché restano operazioni da fare.
- In ogni step si aggiungono, nell'ordine (livello crescente, poi codice), tutte le operazioni di quel tipo già eseguibili, comprese quelle rese possibili dalle righe precedenti dello stesso file (D7).
- Uno step senza righe viene saltato.
- Le modifiche delle descrizioni sono sempre l'ultimo step.
- Se in un ciclo completo non si esegue nulla ma restano operazioni, il piano **non viene generato**: si elencano le sedi bloccate e il motivo (dipendenza circolare o dati incoerenti).

Questo copre i casi della sezione 3:
- creazione fase 1 → modifiche → creazione fase 2 (3.2);
- figli spostati prima della rimozione del padre (3.4);
- transcodifica automatica dei codici (3.4).

### 5.4 Contenuto dei file
| Step | File | Righe |
|---|---|---|
| Creazione | `ZPM4R_CREA_FL_crea_upload_Step_<n>.txt` | **Rimandato** (D12). Lo step compare nel piano con l'elenco e il conteggio ma senza file; può essere segnato come eseguito a mano. |
| Modifica | `CC04_modificare_upload_Step_<n>.xls` | Functional Location = codice **attuale nel momento dello step** (transcodificato); New Code = Nuova sede tecnica; Description = Nuova descrizione; New Superior = padre del New Code |
| Rimozione | `CC04_rimuovere_upload_Step_<n>.xls` | Functional Location = codice attuale nel momento dello step; New Code = stesso codice con `A` come 3° carattere del 1° livello; Description = Descrizione; New Superior = radice del cestino (es. `USA`) |
| Modifica descrizione | `ZPM4R_CREA_FL_modifica_upload_Step_<n>.txt` | TPLNR, PLTXT, COUNTRY |

Per ogni step la GUI mostra il numero di righe e le sedi completate per propagazione.

### 5.5 Esecuzione nella GUI
- **Stato di ogni step:** Da caricare → Caricato (da validare) → Validato / Con errori.
- Si può caricare solo il primo step non validato.
- Il pulsante "Carica in SAP" avvierà gli script, da definire. Fino ad allora c'è **"Segna come caricato"**, per i caricamenti fatti a mano con la transazione.
- Dalla prima validazione il piano è in esecuzione e i dati sono bloccati (D10).

## 6. Impatti sul codice esistente

- **No_Wo (D2):** `Progetto.sedi_per_no_wo()` restituisce solo le sedi "Da rimuovere". Se non ce ne sono, No_Wo è subito "Aggiornata", senza estrazione. Da aggiornare anche:
  - il test `test_flusso_completo`;
  - la descrizione della scheda;
  - SPECIFICHE_GUI.md, 4.6.
- **Riconciliazione: nessuna modifica.** Il caso "codice occupato da una sede da rimuovere" (domanda 3.2 precedente) non può presentarsi: una destinazione è sempre un codice di New, e una sede presente in New non può essere "Da rimuovere" (resta "Da verificare"). L'ordine delle operazioni lo garantisce la simulazione.
- **Specifiche:** SPECIFICHE_GUI.md, sezione 7, punto "cancellare o spostare": chiuso con D1.
- **Nuovo codice:**
  - `conversione_sedi/piano_sap.py`: simulazione e piano, senza GUI;
  - `conversione_sedi/file_sap.py`: scrittura dei file;
  - `Scheda.SAP_SCRIPT` in `progetto.py`, con il piano salvato nel `.bessprj`, gli stati degli step e il blocco dei dati;
  - pagina in `gui/pagine.py`.

## 7. Note per la ripresa

- **Modifiche locali dell'utente non incluse nei commit:** `conversione_sedi/config/regole.csv`, `conversione_sedi/config/trasformazioni.csv` e la copia di backup delle regole originali, rinominata dall'utente da `regole_rack.csv` a `regole_back.csv`. Non vanno toccati né inclusi nei commit senza chiedere. Il file di backup non è usato dal programma, che legge solo `config/regole.csv`.
- **`specifiche_integrative.md`:** il suo contenuto è integrato nella sezione 3.
- **Test:** eseguirli con `.venv\Scripts\python.exe -m pytest` dalla cartella `conversione_sedi`; ultimo esito: 192 test superati.
