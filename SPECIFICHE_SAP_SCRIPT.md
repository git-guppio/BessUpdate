# Step "SAP script" — richiesta, analisi e domande aperte

> **Destinatario:** Claude Code e l'utente, per riprendere il lavoro.
> **Stato:** informazioni dell'utente del 20/10 integrate (sezione 3); restano le domande aperte della **sezione 5**. **Non è stato ancora scritto codice** per questo step.
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

## 4. Proposta: piano di caricamento calcolato dal programma

Le regole del capitolo 3 dipendono una dall'altra:
- una creazione può dipendere da una modifica (3.2);
- una modifica può dipendere da una creazione, perché il nuovo genitore deve esistere;
- una modifica può dipendere da una rimozione, che libera il codice di destinazione;
- con la propagazione attiva, una rimozione o una modifica di un padre cambia i codici dei figli (3.4).

Un ordine fisso dei file non basta in tutti i casi. Propongo quindi che il programma **simuli in sequenza** le operazioni sulla struttura attuale e costruisca un **piano a fasi**. Per ogni fase:
- controlla che il **genitore esista** (per creazioni e modifiche) e che il **codice di destinazione sia libero**;
- se la propagazione è attiva, calcola il **codice che ogni sede avrà in quel momento** (transcodifica automatica, 3.4);
- inserisce in una fase solo le operazioni già eseguibili e rimanda le altre alla fase successiva;
- se a un certo punto nessuna operazione è più eseguibile (dipendenza circolare), si ferma e **segnala le sedi bloccate**, invece di produrre file che fallirebbero in SAP.

Esempio di piano, **con propagazione disattivata** (vedi domanda 5.2):

| Fase | File | Contenuto |
|---|---|---|
| 1 | `CC04_rimuovere_upload.xls` | Rimozioni (spostamento in `xxA-…`): liberano i codici |
| 2 | `ZPM4R_CREA_FL_crea_upload.txt` | Creazioni fase 1: genitore esistente o creato prima nello stesso file (ordinate per livello) |
| 3 | `CC04_modificare_upload.xls` | Modifiche: dall'alto verso il basso e secondo la colonna "Sequenza", in modo che genitore e codice libero siano garantiti |
| 4 | `ZPM4R_CREA_FL_crea_upload_2.txt` | Creazioni fase 2: genitore ottenuto da una modifica della fase 3 |
| 5 | `ZPM4R_CREA_FL_modifica_upload.txt` | Modifiche delle sole descrizioni (nessuna dipendenza) |

Se servono altre fasi, ad esempio una modifica che richiede un genitore creato in fase 4, il piano le aggiunge con il suffisso `_3`, `_4`, … (vedi domanda 5.3).

**Nella GUI:** lo step mostra il piano come elenco ordinato dei file, ciascuno con il conteggio delle sedi e il pulsante di caricamento. I pulsanti si attivano **uno alla volta, nell'ordine**, perché ogni file presuppone che i precedenti siano stati caricati (vedi domanda 5.5).

## 5. Domande aperte

### 5.1 "Eliminazione" = "Da rimuovere"? Chiusura degli ordini: blocco o avviso? — **importante**
Nel programma "Da rimuovere" significa **spostamento** nella struttura `xxA-…` tramite CC04, cioè una **modifica dell'etichetta**. Secondo 3.1 l'ID interno resta lo stesso, e ordini e avvisi seguirebbero la sede nella struttura `USA-…`. Il testo del 20/10 parla invece di "eliminazione e successiva ricreazione".

Domande:
- Confermi che le sedi da cui chiudere ordini e avvisi sono **esattamente quelle "Da rimuovere"**? La chiusura serve perché non restino lavori aperti su sedi dismesse, anche se tecnicamente l'ID non cambia.
- Esiste anche il caso **"eliminare e ricreare"**, cioè rimuovere una sede e crearne una nuova con lo **stesso codice**? Oggi la riconciliazione non lo produce mai: una sede presente sia in SAP sia in New resta invariata.
- Con ordini o avvisi ancora aperti su sedi da rimuovere, la generazione del file `CC04_rimuovere_upload.xls` deve essere **bloccata** (consigliato, visto che vanno chiusi prima) oppure solo **segnalata**?

**Risposta:** _…_

### 5.2 La propagazione ai figli in CC04 viene attivata o no? — **fondamentale**
Secondo 3.4 la CC04 massiva "consente" la propagazione, quindi è un'opzione. La scelta cambia completamente l'ordine e il contenuto dei file.
- **Propagazione disattivata (consigliata):** ogni riga sposta una sola sede e i codici delle altre restano quelli della lista originale. Non serve transcodifica.
  - Le rimozioni possono andare per prime e liberano i codici.
  - Un figlio da modificare sotto un padre rimosso resta con il suo codice e viene spostato dalla propria riga di modifica.
  - Il piano della sezione 4 funziona così com'è.
- **Propagazione attiva:** rinominando o rimuovendo un padre cambiano anche i codici dei figli.
  - Le righe dei figli vanno scritte con il codice transcodificato, oppure tolte se la propagazione produce già il codice voluto.
  - Rimuovere un padre porterebbe nella struttura `USA-…` anche i figli che dovevano solo essere spostati altrove: quei figli vanno modificati **prima** della rimozione del padre.
  - Il programma può gestirlo con la simulazione, ma il piano diventa più complesso e più fragile se SAP si comporta in modo leggermente diverso.

Quale modalità userai? Se la propagazione è un'opzione dello script o della transazione, la scelta potrà essere fissata negli script che mi descriverai.

**Risposta:** _…_

### 5.3 Nomi dei file quando le fasi sono più di una
I nomi richiesti sono fissi (`ZPM4R_CREA_FL_crea_upload.txt`, …). Con creazioni in più fasi servono nomi distinti. Proposte:
- **(a)** suffisso di fase, `ZPM4R_CREA_FL_crea_upload_2.txt`;
- **(b)** prefisso con il numero d'ordine del piano per **tutti** i file, es. `1_CC04_rimuovere_upload.xls`, `2_ZPM4R_CREA_FL_crea_upload.txt`, … Rende l'ordine di caricamento evidente anche nella cartella.

Gli script SAP che descriverai devono leggere questi nomi: quale convenzione preferisci?

**Risposta:** _…_

### 5.4 Righe in ordine nello stesso file
Consiglio di inserire nello stesso file della fase 1 un genitore e un figlio entrambi da creare, con il genitore prima del figlio. Funziona solo se `ZPM4R_CREA_FL` e CC04 elaborano le righe **una alla volta, nell'ordine del file**.
- È così?
- Se una riga fallisce, le successive vengono comunque elaborate?

**Risposta:** _…_

### 5.5 Caricamento in sequenza e verifica tra una fase e l'altra
Proposta:
- i pulsanti di caricamento si attivano nell'ordine del piano;
- il file n si carica solo dopo il file n-1;
- dopo ogni caricamento si può (facoltativamente) rilanciare l'estrazione IH06 della scheda Check per verificare l'esito prima di passare alla fase successiva.

Va bene? Oppure preferisci poter caricare i file liberamente?

**Risposta:** _…_

### 5.6 Domande precedenti ancora senza risposta
Se non ci sono preferenze si procede con la proposta indicata.

| Domanda | Proposta |
|---|---|
| **Dove va il pulsante di creazione dei file?** La richiesta del 19/10 lo colloca nella scheda "SAP Actual". | Nello step **SAP script**: probabilmente "SAP Actual" è un refuso. |
| **Sedi da creare.** "Da creare" non è un valore di "Operazione": le sedi da creare vengono da **Check New** (Stato = "Da creare"). | Il contenuto del file è rimandato. Lo step mostra comunque le creazioni nel piano, con il conteggio e la nota "file non ancora disponibile". |
| **Dati cambiati dopo la generazione** (nuova decisione o estrazione). | Lo step passa a ⚠ "Da aggiornare" e i caricamenti restano disattivati finché i file non vengono rigenerati. |
| **Caso limite rimozioni:** il primo livello ha già `A` come terzo carattere (es. `ITA-…`). | Errore bloccante: il nuovo codice coinciderebbe con l'attuale. |
| **Caso limite rimozioni:** il codice `xxA-…` esiste già in SAP (da una rimozione precedente). | Il programma non può verificarlo, perché IH06 estrae solo l'impianto: si può solo avvisare. |
| Cartella dei file | Sottocartella `SAP_<impianto>` accanto al file `.bessprj`; ogni generazione sovrascrive i file precedenti. |
| File `.txt` | Windows-1252 senza BOM, righe CRLF, intestazione identica al template (tabulazioni e spazio finale compresi), campi non richiesti vuoti. |
| File `.xls` | Formato Excel 97-2003 con `xlwt` (da aggiungere a `pyproject.toml`), foglio `Foglio1`, celle di testo. |
| Descrizioni | Avviso per le descrizioni più lunghe di 40 caratteri, il limite di `PLTXT`. |
| COUNTRY | Primi due caratteri del primo livello (`USE` → `US`). |
| Template | Intestazioni copiate in `conversione_sedi/config/`, indipendenti da `template_SAP/`. |

**Risposta:** _…_

## 6. Impatti sul codice esistente (da fare quando le domande sono chiuse)

- **No_Wo:** `Progetto.sedi_per_no_wo()` deve restituire solo le sedi "Da rimuovere" (3.1). Da aggiornare anche:
  - il test `test_flusso_completo` in `tests/test_progetto.py`;
  - la descrizione della scheda No_Wo in `gui/pagine.py`;
  - SPECIFICHE_GUI.md, 4.6.
- **Riconciliazione:** se la rimozione per rinomina libera il codice (vero in entrambe le modalità della 5.2, purché la rimozione avvenga prima della modifica che riusa il codice), la regola "codice occupato da una sede da rimuovere" va rimossa. Riguarda:
  - `riconciliazione.py`, `_risolvi_destinazioni`, punto 3;
  - il test `test_codice_occupato_da_sede_da_rimuovere`;
  - SPECIFICHE_GUI.md, 4.4.

  Con la propagazione attiva va verificato che la sede liberata non abbia figli che la seguono.
- **Specifiche:** SPECIFICHE_GUI.md, sezione 7, punto "cancellare o spostare": chiuso, rimozione = spostamento nella struttura `xxA-…` con CC04, New Superior = primo livello.
- **Nuovo codice:**
  - voce `Scheda.SAP_SCRIPT` in `progetto.py`, tra `NO_WO` e `CHECK`, con il suo stato;
  - pagina in `gui/pagine.py`;
  - modulo senza GUI per piano e file (es. `conversione_sedi/piano_sap.py` per la simulazione a fasi e `conversione_sedi/file_sap.py` per la scrittura dei file), testabile con pytest.
- **Dati di partenza:**
  - `Progetto.riconciliazione().actual`, colonne `Sede tecnica`, `Descrizione`, `Operazione`, `Nuova sede tecnica`, `Nuova descrizione`, `Sequenza`;
  - `Progetto.riconciliazione().new`, colonna `Stato`, per le sedi da creare.

## 7. Note per la ripresa

- **Modifiche locali dell'utente non incluse nei commit:** `conversione_sedi/config/regole.csv`, `conversione_sedi/config/trasformazioni.csv` e la copia di backup delle regole originali, rinominata dall'utente da `regole_rack.csv` a `regole_back.csv`. Non vanno toccati né inclusi nei commit senza chiedere. Il file di backup non è usato dal programma, che legge solo `config/regole.csv`.
- **`specifiche_integrative.md`:** il suo contenuto è integrato nelle sezioni 3 e 4.
- **Test:** eseguirli con `.venv\Scripts\python.exe -m pytest` dalla cartella `conversione_sedi`; ultimo esito: 192 test superati.
