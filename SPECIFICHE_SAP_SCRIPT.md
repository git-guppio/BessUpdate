# Step "SAP script" — richiesta, analisi e domande aperte

> **Destinatario:** Claude Code e l'utente, per riprendere il lavoro.
> **Stato:** in attesa delle risposte dell'utente alle domande della sezione 3 (raccolta di informazioni in corso). **Non è stato ancora scritto codice** per questo step.
> **Data:** 20/10/2026. Ultimo commit al momento della stesura: `fc970b3` (GUI con tema chiaro fisso).

---

## 1. Richiesta dell'utente (19/10/2026)

**Nuovo step "SAP script"** nella barra laterale, dopo **7. No_Wo** e prima di **8. Check**:
- crea i file di caricamento in SAP;
- avvia gli script SAP che leggono quei file.

**Pulsanti:**
- un pulsante crea i file per modifica, cancellazione e creazione dei dati in SAP. Nella richiesta è collocato nella scheda "SAP Actual": vedi domanda 5;
- al termine della creazione si attiva un pulsante di caricamento **solo per i file effettivamente creati**. Il pulsante avvia gli script SAP che leggono quei file; gli script verranno specificati in seguito;
- per ogni file creato viene indicato quante sedi tecniche saranno rimosse, modificate, rinominate o create.

**File da creare**, in base alla colonna **"Operazione"** della scheda Check Actual:

| Operazione | File | Formato | Contenuto |
|---|---|---|---|
| Modifica descrizione | `ZPM4R_CREA_FL_modifica_upload.txt` | Testo separato da tabulazioni, intestazioni come `template_SAP/ZPM4R_CREA_FL_Template.txt`. Transazione `ZPM4R_CREA_FL` in modalità modifica | Valorizzati solo: `TPLNR` = Sede tecnica; `PLTXT` = nuova descrizione; `COUNTRY` = primi due caratteri del primo livello (`USE-US64-1A` → `US`) |
| Da rimuovere | `CC04_rimuovere_upload.xls` | Excel `.xls`, intestazioni come `template_SAP/CC04_Template.xls` | Vedi sotto |
| Modifica | `CC04_modificare_upload.xls` | Excel `.xls`, intestazioni come `template_SAP/CC04_Template.xls` | Vedi sotto |
| Da creare | `ZPM4R_CREA_FL_crea_upload.txt` | Testo separato da tabulazioni, intestazioni come il template ZPM4R | **Rimandato**: la logica è complessa e verrà definita in seguito |

**Rimozione (CC04):** si sposta la sede in una nuova struttura, sostituendo il **terzo carattere del primo livello** con `A`.

| Colonna | Valore | Esempio |
|---|---|---|
| Functional Location | Sede tecnica | `USE-US64-1E-02-B4` |
| New Code | Sede con il 3° carattere del 1° livello sostituito da `A` | `USA-US64-1E-02-B4` |
| Description (if required) | Descrizione | `Battery Bank 3 of Container 03` |
| New Superior | **Solo il primo livello** modificato | `USA` |

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
- Nel `.venv` non ci sono librerie per i file `.xls`. Servirà `xlwt` per scriverli; `xlrd` è stato usato solo per leggere il template, in una cartella temporanea.

## 3. Domande aperte (da risolvere prima di scrivere il codice)

I punti 1–4 sono i più importanti: da essi dipende se i file caricati in SAP funzionano davvero.

### 3.1 SAP rinomina automaticamente le sedi sottostanti? — **fondamentale**
Se con CC04 si cambia il codice di una sede padre (es. `…-1E-01-B1` → `…-1E-01-C1`), le sedi figlie vengono rinominate in automatico (`…-B1-BM` → `…-C1-BM`)?
- **Se sì:**
  - la riga del figlio nel file (`…-B1-BM` → `…-C1-R1`) fallirebbe, perché `…-B1-BM` non esiste più;
  - occorre rinominare prima i figli e poi i padri, cioè ordinare il file dal basso verso l'alto;
  - nelle rimozioni, rimuovere un padre trascinerebbe anche i figli, che magari andavano solo modificati.
- **Se no:** si procede dall'alto verso il basso, così ogni "New Superior" esiste già quando serve.

**Risposta:** _…_

### 3.2 La rimozione per rinomina libera il codice originale
Oggi la riconciliazione considera "occupato" il codice di una sede da rimuovere, perché si pensava a un contrassegno di cancellazione. Il caso è descritto in SPECIFICHE_GUI.md, 4.4, ed è implementato in `riconciliazione.py`, `_risolvi_destinazioni`, punto 3.

Con la rimozione per rinomina verso `USA-…` il codice originale **si libera**. Esempio: X da rimuovere e Z → X. Oggi è un *Conflitto*; diventerebbe valido se la rimozione viene eseguita prima della modifica.

**Consiglio:** aggiornare la regola (una sede da rimuovere libera il suo codice) e caricare le rimozioni prima delle modifiche. Dipende dalla 3.1. Se la regola cambia, vanno aggiornati anche i test `test_codice_occupato_da_sede_da_rimuovere` e la sezione 4.4 delle specifiche.

**Risposta:** _…_

### 3.3 "New Superior" delle rimozioni = solo la radice?
Nell'esempio il New Code `USA-US64-1E-02-B4` ha New Superior `USA` e non `USA-US64-1E-02`.
- È voluto? Il vantaggio è che non servono sedi intermedie `USA-…` già esistenti in SAP.
- La radice `USA` **esiste già in SAP**? Altrimenti tutte le righe falliscono.

Casi limite proposti:
- se il New Code `USA-…` esiste già in SAP (es. da una rimozione precedente) la riga fallisce. Il programma non può verificarlo, perché l'estrazione IH06 riguarda solo `USE-…*`: si può solo avvisare;
- se il terzo carattere del primo livello è già `A` (es. impianto `ITA-…`), il New Code coinciderebbe con il codice attuale. Proposta: errore bloccante.

**Risposta:** _…_

### 3.4 Ordine di caricamento dei file e "New Superior" delle modifiche
Il New Superior di una modifica è il parent del nuovo codice e deve **già esistere** quando CC04 elabora la riga. Quel parent potrebbe però essere:
- **da creare**: la creazione va fatta prima;
- **a sua volta modificato**: va prima la rinomina del parent;
- **liberato da una rimozione**: va prima la rimozione.

Proposta di ordine, da confermare dopo la 3.1:
1. rimozioni;
2. creazioni (dall'alto in basso);
3. modifiche, ordinate per livello e per la colonna "Sequenza" della riconciliazione;
4. modifiche delle descrizioni.

Possibile dipendenza circolare: una creazione sotto un padre che viene rinominato. Può capitare?

**Risposta:** _…_

### 3.5 Dove va il pulsante di creazione dei file?
La richiesta lo colloca nella scheda **"SAP Actual"**, ma lo step **"SAP script"** serve proprio a creare e caricare i file. Presumibilmente è un refuso e il pulsante va in **SAP script**.

**Risposta:** _…_

### 3.6 "Da creare" non è un valore di "Operazione"
"Operazione" (Check Actual) riguarda solo le sedi già in SAP. Le sedi da creare sono nella vista **Check New**, con `Stato = "Da creare"`. Il file di creazione verrà quindi da Check New. È rimandato; intanto lo step mostrerà il conteggio delle sedi da creare con la nota "file non ancora disponibile".

**Risposta:** _…_

### 3.7 Quando si possono generare i file
Già deciso: generazione **bloccata** se ci sono righe Da decidere, Da verificare o Conflitto (SPECIFICHE_GUI.md, 4.4 e 4.7).

Da decidere:
- **Sedi con ordini o avvisi aperti (No_Wo).** Consiglio: non bloccare, ma avvisare e segnalarle nel riepilogo. In alternativa si possono escludere dai file. Quale preferisci?
- **Dati cambiati dopo la generazione** (nuova decisione, nuova estrazione). Consiglio: lo step passa a ⚠ "Da aggiornare" e il caricamento resta disattivato finché i file non vengono rigenerati, così in SAP non finiscono file vecchi.

**Risposta:** _…_

### 3.8 Dettagli tecnici — se non ci sono preferenze si procede così

| Punto | Proposta |
|---|---|
| Cartella dei file | Sottocartella `SAP_<impianto>` accanto al file di progetto `.bessprj`. I nomi sono fissi, come richiesto, e ogni generazione sovrascrive i file precedenti. |
| File `.txt` | Codifica Windows-1252 senza BOM, righe CRLF, intestazione identica al template (tabulazioni e spazio finale compresi), campi non richiesti vuoti. Il formato UTF-8 potrebbe dare problemi con i caratteri accentati in SAP. |
| File `.xls` | Vero formato Excel 97-2003 scritto con `xlwt` (da aggiungere a `pyproject.toml`, non richiede Excel). Foglio `Foglio1`, celle in formato testo. |
| Descrizioni | Avviso per le descrizioni più lunghe di 40 caratteri, il limite di `PLTXT` in SAP. |
| COUNTRY | Primi due caratteri del primo livello (`USE` → `US`). |
| Pulsanti di caricamento | Uno per file generato, con il conteggio (es. "CC04_modificare_upload.xls — 124 sedi da rinominare"), attivi solo per i file creati. Finché gli script non esistono mostrano "script non ancora disponibile". |
| Template | Intestazioni copiate nella cartella `conversione_sedi/config/`, così il programma non dipende dalla cartella `template_SAP/`. |

**Risposta:** _…_

## 4. Note per la ripresa

- **Modifiche locali dell'utente non incluse nei commit:** `conversione_sedi/config/regole.csv`, `conversione_sedi/config/trasformazioni.csv` e il nuovo file `conversione_sedi/config/regole_rack.csv`. Non vanno toccati né inclusi nei commit senza chiedere.
- **Dove si inserirà lo step nel codice:**
  - nuova voce `Scheda` in `conversione_sedi/progetto.py`, tra `NO_WO` e `CHECK`, con il suo stato;
  - nuova pagina in `conversione_sedi/gui/pagine.py`, da aggiungere a `PAGINE`;
  - generazione dei file in un nuovo modulo senza dipendenze dalla GUI (es. `conversione_sedi/file_sap.py`), testabile con pytest.
- **Dati di partenza:**
  - `Progetto.riconciliazione().actual`, colonne `Sede tecnica`, `Descrizione`, `Operazione`, `Nuova sede tecnica`, `Nuova descrizione`, `Sequenza`;
  - `Progetto.riconciliazione().new`, colonna `Stato`, per le sedi da creare.
- **La domanda 3.3 chiude un punto aperto delle specifiche:** la scelta tra "cancellare e spostare" (SPECIFICHE_GUI.md, sezione 7) diventa "rimozione = spostamento nella struttura `xxA-…` tramite CC04". Va aggiornata la sezione 7.
- **Test:** eseguirli con `.venv\Scripts\python.exe -m pytest` dalla cartella `conversione_sedi`; ultimo esito: 192 test superati.
