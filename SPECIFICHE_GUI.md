# Interfaccia grafica — Specifiche consolidate

> **Destinatario:** Claude Code.
> Il documento raccoglie le decisioni prese con l'utente a partire da `Specifiche generali.md` e ne costituisce l'evoluzione. La logica di conversione delle Sedi tecniche è descritta in `SPECIFICHE_CONVERSIONE_SEDI.md` ed è già implementata nel pacchetto `conversione_sedi` (non va duplicata nella GUI).
>
> Ogni punto è contrassegnato con:
> - **[Deciso]** — confermato dall'utente;
> - **[Proposta]** — suggerito e non ancora confermato: va confermato prima dell'implementazione;
> - **[Da definire]** — informazione mancante (vedi sezione 7).

---

## 1. Obiettivo

Le Sedi tecniche di un impianto presenti in SAP sono state ricodificate secondo nuove regole. La nuova codifica proposta è fornita in un file Excel (scheda **New**). Il programma deve allineare i dati presenti in SAP (scheda **Actual**) con quelli proposti, determinando:

- i codici esistenti da **modificare**;
- i codici non più necessari da **cancellare o spostare**;
- i nuovi codici mancanti da **creare**.

Al termine si devono ottenere i file per il caricamento in SAP e, dopo il caricamento, poter **verificare** che SAP corrisponda esattamente alla codifica di New (scheda **Check**).

## 2. Concetti

| Termine | Significato |
|---|---|
| **Livello** | Numero di segmenti della Sede tecnica = occorrenze di `-` + 1. `ITE` = 1, `ITE-OT0B` = 2, `ITE-OT0B-1E-01-B1-BM` = 6. |
| **Impianto** | Primi due livelli della Sede tecnica (es. `ITE-OT0B`). |
| **Parent** | Sede tecnica ottenuta togliendo l'ultimo segmento (`ITE-OT0B-1E-01-B1-BM` → `ITE-OT0B-1E-01-B1`). Il livello 1 non ha parent. |
| **Dato importato** | Riga o cella proveniente da file Excel o da SAP. |
| **Dato manuale** | Riga inserita o cella modificata dall'utente. |

## 3. Regole generali (valide per tutte le schede)

### 3.1 Sequenza dei passaggi e aggiornamento a cascata — [Deciso]

- L'ordine di esecuzione dei passaggi è vincolato: una scheda è utilizzabile solo se i passaggi da cui dipende sono stati eseguiti.
- Se una riga di una scheda viene modificata, le schede successive devono essere aggiornate di conseguenza.

Dipendenze:

```
New ──► Actual ──► FL da creare ──► Riconciliazione ──► Check Parent ──► No_Wo ──► File SAP
 │                                  (Check New /
 │                                   Check Actual)
 └──────────────────────────────────────────────────────────────────────────────► Check
```

**[Proposta]** Modalità di aggiornamento:

| Stato della scheda | Significato | Indicazione |
|---|---|---|
| Bloccata | Passaggi precedenti non eseguiti | Scheda disattivata, icona 🔒 |
| Aggiornata | Calcolata sui dati correnti | Icona ✓ |
| Da aggiornare | Un passaggio precedente è cambiato | Icona ⚠ |

- I **passaggi locali** (conversione, riconciliazione, Check Parent, esiti della scheda Check) vengono ricalcolati **automaticamente**.
- I **passaggi che interrogano SAP** (Actual, No_Wo, estrazione della scheda Check) **non** vengono ripetuti automaticamente: la scheda passa a "Da aggiornare" e l'utente rilancia l'estrazione.

### 3.2 Impianto unico — [Deciso]

La lista riguarda un solo impianto: tutte le Sedi tecniche devono avere gli stessi primi due livelli. Una differenza è un errore.

- **Importazione di New:** il controllo è bloccante. Il caricamento viene interrotto e il messaggio elenca le righe non conformi (numero di riga Excel e valore), prendendo come riferimento l'impianto più frequente.
- **[Proposta]** Lo stesso controllo si applica:
  - alle modifiche manuali di New (una modifica che cambia impianto viene rifiutata);
  - ai dati estratti da SAP (Actual e Check);
  - alla conversione: se una Nuova Sede tecnica avesse un impianto diverso, l'esito diventa `DA_VERIFICARE`.
- **[Proposta]** Le righe di livello 1 e 2 (es. `ITE`, `ITE-OT0B`) sono ammesse se coerenti con l'impianto.
- **[Proposta]** Caricare un file New di un **altro impianto** azzera tutto il lavoro, previa conferma dell'utente.

### 3.3 Dati manuali — [Deciso]

- I dati inseriti o modificati manualmente devono essere **conservati** anche quando le schede vengono ricalcolate.
- **Colore del testo:** **nero** per i dati importati, **blu** per i dati manuali.
- Possono essere previste etichette in colonne aggiuntive.

**[Proposta]** Dettagli:

- **Colori:** il colore del **testo** indica l'origine del dato; il colore di **sfondo** della riga indica l'esito dei controlli. In questo modo origine ed esito sono visibili insieme. Valori di sfondo: nessuno = OK; rosso chiaro = errore; giallo = da verificare.
  > Nota: `Specifiche generali.md` prevedeva testo rosso per "Parent NOK" e "Valore duplicato"; con questa proposta il rosso diventa lo sfondo della riga.
- **Righe inserite a mano:** interamente in blu.
- **Celle importate e poi modificate:** solo la cella in blu. Al passaggio del mouse si vede il valore originale e il comando "Ripristina valore originale" la riporta al dato importato.
- **Colonna "Origine":** `IMPORTATO` / `MANUALE` / `MODIFICATO` / `RIMOSSO`. Rimane nell'esportazione e negli appunti, dove i colori si perdono.
- **Colonna "Note":** testo libero.
- **Correzioni nelle schede derivate:** sono legate alla Sede tecnica di Actual da cui provengono e vengono riapplicate a ogni ricalcolo. Se quella Sede tecnica non esiste più, la correzione viene segnalata come **"correzione orfana"**, da confermare o eliminare.
- Nell'esportazione Excel i colori vengono riprodotti.

**[Deciso]** Righe rimosse:
- una riga **importata** rimossa dall'utente non viene cancellata: resta visibile, barrata in grigio, con Origine = `RIMOSSO`, è esclusa dai calcoli e può essere ripristinata;
- una riga **inserita a mano** viene invece cancellata davvero.

**[Deciso]** Nuova importazione di New (stesso impianto) o nuova estrazione di Actual in presenza di dati manuali: il programma **chiede ogni volta** all'utente se conservare o scartare le modifiche manuali.
- **[Proposta]** Il messaggio indica quante modifiche manuali esistono, ad esempio *"Sono presenti 37 modifiche manuali (12 in New, 25 in FL da creare). Conservarle?"*.
- **[Proposta]** Se l'utente sceglie di conservarle, quelle non più applicabili vengono segnalate come "orfane".

### 3.4 Modifica delle tabelle — [Deciso]

Ogni tabella deve permettere l'inserimento e la rimozione di righe, secondo le regole del punto 3.3.

### 3.5 Menu contestuale — [Deciso]

Ogni tabella ha un menu contestuale con:
- copia dell'intera tabella negli appunti;
- copia della riga su cui si trova il mouse.

**[Proposta]**
- Aggiungere anche "copia righe selezionate" e "copia cella".
- Formato degli appunti: testo separato da tabulazioni con intestazioni, incollabile direttamente in Excel.

### 3.6 Altre funzioni comuni — [Proposta]

- Pulsante "Esporta" (Excel) in tutte le tabelle.
- Filtro e ricerca in ogni tabella.
- Barra di stato con i conteggi della scheda attiva.
- **Salva / Apri sessione:** necessario per non perdere i dati manuali e le estrazioni SAP alla chiusura del programma.

## 4. Schede

### 4.1 New — [Deciso]

- **Contenuto:** la nuova codifica proposta, da applicare ai dati presenti in SAP. Colonne: **"Sede tecnica"** e **"Descrizione"**.
- **Caricamento:** da file Excel tramite pulsante.
- **Controlli bloccanti:** in caso di errore il caricamento viene interrotto con un messaggio.
  - presenza delle due colonne con intestazione;
  - impianto unico (3.2).
- **[Proposta]**
  - Colonne individuate per nome dell'intestazione: senza distinzione tra maiuscole e minuscole, colonne aggiuntive ignorate.
  - Avvisi non bloccanti per righe vuote e Sedi tecniche duplicate.
  - Normalizzazione: spazi esterni rimossi, conversione in maiuscolo.

### 4.2 Actual — [Deciso]

- **Contenuto:** i dati presenti in SAP, base di partenza per la pianificazione. Colonne: **"Sede tecnica"** e **"Descrizione"**.
- **Caricamento:** prelevati da SAP leggendo i dati dell'impianto, cioè il secondo livello dei codici di New.
- **[Deciso] Estrazione:** transazione **IH06**.
  - Campo Sede tecnica = `<impianto>*` (es. `USE-USS5*`), layout utente **`FL_BESS_MIG`**.
  - La lista viene esportata negli appunti; colonne del layout: "Sede tecnica", "Definizione della sede tecnica", "St.sist.".
  - Al termine si controlla la barra di stato per rilevare eventuali errori.
  - **Filtro sullo stato di sistema:** sono **escluse** le Sedi tecniche il cui stato contiene **`CANC`**, **`OGIN`** o **`FCAN`** (voce intera, non parte di un'altra abbreviazione).
  - Implementazione: `conversione_sedi.sap.estrai_sedi_ih06`.
- Actual **non** viene sovrascritto dalle estrazioni di verifica, che popolano la scheda Check (4.8).
- **[Proposta]** Una nuova estrazione di Actual, ad esempio per ripartire dalla situazione corrente di SAP, richiede conferma, perché le correzioni manuali delle schede derivate potrebbero diventare orfane.

### 4.3 FL da creare (conversione)

- **[Deciso]** Colonne: "Sede tecnica" (da Actual), "Codice_Out", "Nuove sedi tecniche", "Esito", con il significato definito in `SPECIFICHE_CONVERSIONE_SEDI.md`. Calcolo affidato a `conversione_sedi.elabora_dataframe`.
- **[Proposta]**
  - Colonna "Descrizione" riportata da Actual: serve per i file SAP.
  - Colonna "Correzione manuale", che ha la precedenza sul risultato automatico e serve a risolvere gli esiti `DA_VERIFICARE`.
  - Sfondo giallo per `DA_VERIFICARE`, grigio per `NESSUNA_CORRISPONDENZA`.
- **[Deciso] Identità prima della conversione:** una Sede tecnica di Actual già presente identica in New è considerata "già allineata" e non viene convertita. Se però la conversione la porterebbe su un altro codice anch'esso presente in New, la riga viene segnalata come **conflitto** da risolvere a mano (4.4).
  > Questa regola appartiene al livello di riconciliazione: il nucleo `conversione_sedi.nucleo` resta invariato.

### 4.4 Riconciliazione: Check New e Check Actual — [Deciso]

Confronto tra la conversione di Actual e New, da cui derivano le operazioni SAP:

| Caso | Operazione |
|---|---|
| Sede di Actual convertita in un codice **presente in New** e diverso dall'originale | **MODIFICA** |
| Sede di Actual già identica a un codice di New | Nessuna, oppure solo modifica della descrizione se diversa da New |
| Sede di New **non raggiunta** da alcuna conversione | **CREA** |
| Sede di Actual convertita in un codice **non presente in New** | **CANCELLA / SPOSTA** |
| Sede di Actual con esito `NESSUNA_CORRISPONDENZA` | **CANCELLA / SPOSTA**, oppure da verificare |
| Più Sedi di Actual convertite nella **stessa** nuova Sede | **Conflitto**: decisione manuale (vedi sotto) |

**[Deciso]** Conflitti N→1:
- le righe coinvolte sono evidenziate come **"Conflitto"**;
- l'utente sceglie quale Sede di Actual viene modificata nella nuova Sede;
- le altre diventano "da cancellare/spostare";
- il programma non sceglie mai in automatico;
- finché esistono conflitti non risolti, la generazione dei file SAP (4.7) è bloccata.

- **Check New:** vista dal lato di New. Per ogni Sede proposta indica se esiste già (e da quale Sede di Actual proviene) o se va creata.
- **Check Actual:** vista dal lato di SAP. Per ogni Sede esistente indica se viene modificata, resta invariata o va cancellata o spostata.

### 4.5 Check Parent

**[Deciso]**
- Colonne: "Nuove sedi tecniche" e "Check".
- Pulsanti: "Check" ed "Esporta".
- **Contenuto:** lo **stato finale** dopo le operazioni, cioè la struttura che esisterà in SAP dopo il caricamento: Sedi modificate, create e invariate, escluse quelle da cancellare o spostare.
  > Sostituisce la regola originale di `Specifiche generali.md` ("Nuova sede tecnica oppure, se assente, la Sede tecnica originale"), che non includeva le Sedi da creare presenti solo in New.
- **Ordine dei controlli:**
  1. Prima si cercano i **duplicati** ("Valore duplicato").
  2. Poi si cercano i **parent** mancanti ("Parent NOK").
- **Regola dei parent:** si risale livello per livello fino alla radice.

**[Proposta]**
- **Parent:** è la Sede tecnica senza l'ultimo segmento. Basta verificare il parent diretto: se manca un antenato più alto, l'errore compare sulla riga del parent.
- **Livelli 1 e 2:** sono considerati esistenti, perché non fanno parte dell'estrazione. Altrimenti genererebbero falsi "Parent NOK".
- **Righe senza Sede valida:** le righe `DA_VERIFICARE` non corrette e le righe vuote sono escluse e segnalate a parte. Il prefisso `DA VERIFICARE: ` non deve entrare nel controllo.
- **Più errori sulla stessa riga:** se una riga è sia duplicata sia senza parent, la colonna Check li riporta entrambi.

### 4.6 No_Wo

**[Deciso]** (da `Specifiche generali.md`):
- Colonne: "Work Order" e "Notification".
- Pulsante "Aggiorna": legge da SAP gli ordini e gli avvisi.
- Pulsante "Esporta": esporta la tabella in Excel.

**[Deciso]**
- **Scopo:** individuare ordini e avvisi aperti che bloccano la cancellazione o la modifica delle Sedi tecniche.
- **Posizione nel flusso:** l'estrazione si esegue **una volta consolidate le modifiche** (dopo la riconciliazione) e riguarda **solo le Sedi tecniche da modificare o cancellare**.
- **Ordini:** transazione **IW39**, layout utente **`OdM_BESS_MIG`**.
  - Flag: aperti, in lavorazione e storici attivi; chiusi esclusi. Date di validità azzerate.
  - Implementazione: `conversione_sedi.sap.estrai_ordini_iw39`.
- **Avvisi:** transazione **IW29**, layout utente **`AdM_BESS_MIG`**.
  - Flag: aperti, rinviati e in lavorazione attivi; chiusi esclusi. Date di validità azzerate.
  - Implementazione: `conversione_sedi.sap.estrai_avvisi_iw29`.
- Le Sedi tecniche vengono passate alla selezione multipla tramite gli appunti.
- **Un solo risultato:** SAP apre direttamente l'ordine o l'avviso; i dati vengono letti dalla videata.
- **Più risultati:** la lista viene esportata negli appunti.
- **Dati restituiti:** Sede tecnica, numero (Work Order o Notification), Descrizione, Stato sistema.

**[Proposta]** Colonne della tabella: "Sede tecnica", "Work Order", "Notification", "Descrizione", "Stato".

### 4.7 File di caricamento SAP

**[Deciso]**
- Le modifiche vengono caricate in SAP tramite una **transazione massiva**.
- Il programma deve produrre un **file Excel** con una struttura specifica **[Da definire]**.
- Un pulsante dedicato avvia la generazione del file.

**[Da definire]**
- tracciato del file Excel;
- se lo stesso file comprende creazioni, modifiche e cancellazioni o se servono file separati.

**[Proposta]** Il pulsante di generazione è disponibile solo quando:
- la riconciliazione è aggiornata;
- non esistono conflitti non risolti;
- non esistono righe `DA_VERIFICARE` non corrette.

**[Proposta]** Ordine delle operazioni nei file:
- creazioni dal livello più alto al più basso (prima i parent);
- cancellazioni dal livello più basso al più alto (prima i figli);
- cancellazioni escluse o segnalate se la Sede è presente in No_Wo.

### 4.8 Check (verifica dopo il caricamento) — [Deciso]

**Scopo.** Verificare, dopo il caricamento in SAP, che tutte le modifiche siano andate a buon fine e che la codifica di New corrisponda esattamente a quella presente in SAP. È una scheda separata per non alterare la base di partenza (Actual).

**Dati:**
- estratti da SAP con la **stessa transazione** usata per Actual;
- **[Proposta]** pulsante "Aggiorna da SAP", ripetibile quante volte serve, con data, ora e impianto dell'estrazione visibili.

**Tabella** (tre colonne):

| Colonna | Contenuto |
|---|---|
| Sede tecnica | Codice estratto da SAP; per le righe "Mancante in SAP", codice di New. |
| Descrizione | Descrizione estratta da SAP; per le righe "Mancante in SAP", descrizione di New. |
| Esito check | Risultato del confronto. |

- Le righe **Mancante in SAP** (presenti in New ma non in SAP) vengono **aggiunte in fondo alla tabella**, con codice e descrizione presi da New.

**Confronto:**
- è **diretto** con New, codice per codice, **senza applicare la conversione**;
- **descrizioni:** si ignorano gli spazi iniziali e finali e gli spazi multipli (ridotti a uno); le **maiuscole contano**.
- **[Deciso]** Ogni altro carattere conta. Ad esempio le virgolette presenti in alcune descrizioni SAP (`"Buildings, Areas and Roads"`) sono refusi da correggere in SAP e devono risultare come `Descrizione diversa`.
- **[Deciso]** Dati estratti con la stessa funzione di Actual (`estrai_sedi_ih06`, IH06 con layout `FL_BESS_MIG` e stesso filtro sugli stati).

**Esiti:**

| Esito | Condizione | Sfondo [Proposta] |
|---|---|---|
| `Allineata` | Codice presente in SAP e in New, stessa descrizione | nessuno |
| `Mancante in SAP` | Codice presente in New, assente in SAP | rosso chiaro |
| `In eccesso in SAP` | Codice presente in SAP, assente in New | rosso chiaro |
| `Descrizione diversa (New: "<descrizione New>")` | Codice presente in entrambi, descrizioni diverse | giallo |

**Pannello statistiche**, a fianco della tabella:
- totale delle righe e conteggio per ciascun esito;
- **[Proposta]**
  - percentuale per esito e percentuale di allineamento (Allineate / totale);
  - un clic su un esito filtra la tabella su quell'esito.

**Dipendenze:**
- la scheda richiede New caricato;
- **[Proposta]** se New viene modificato, gli esiti vengono ricalcolati automaticamente senza una nuova estrazione;
- **[Proposta]** i dati estratti devono rispettare l'impianto unico (3.2).

**[Proposta]**
- Le Sedi contrassegnate per la cancellazione in SAP vanno considerate assenti, se la transazione riporta questo dato.
- Pulsante "Esporta" e menu contestuale, come le altre tabelle.

## 5. Ordine delle schede

**[Proposta]** New → Actual → FL da creare → Check New → Check Actual → Check Parent → No_Wo → Check.

## 6. Tecnologia

**[Deciso]** Comunicazione con SAP tramite **SAP GUI Scripting**: il programma pilota la sessione SAP GUI già aperta dall'utente.

Prerequisiti:
- scripting abilitato sul server (`sapgui/user_scripting`) e sul client SAP GUI;
- una sessione SAP aperta e autenticata;
- **[Deciso]** login in **lingua italiana**: messaggi e stati di sistema vengono interpretati in italiano. Il programma verifica la lingua della sessione;
- **[Deciso]** i layout `FL_BESS_MIG`, `OdM_BESS_MIG` e `AdM_BESS_MIG` sono **layout utente**, per evitare che altri li modifichino. Il programma funziona quindi solo con l'utenza SAP che li possiede (o con utenze che li abbiano creati identici).

**[Proposta]**
- Se non viene trovata alcuna sessione SAP, il programma mostra un messaggio chiaro, senza errori tecnici.
- Se le sessioni aperte sono più di una, l'utente sceglie quale usare.

**[Proposta]**
- **Framework:** PySide6 (Qt), con `QTableView` e un modello basato su DataFrame pandas. Gestisce decine di migliaia di righe, colori per cella, menu contestuali e filtri.
- **Architettura:**
  - logica separata dall'interfaccia: conversione in `conversione_sedi.nucleo`, riconciliazione e controlli in moduli dedicati e testati senza GUI;
  - comunicazione con SAP in un thread separato, con barra di avanzamento e possibilità di annullare.

## 7. Punti da definire

1. **Tracciato del file Excel** per la transazione massiva (4.7) e numero di file da produrre.
2. **Criterio** per scegliere tra cancellazione e spostamento, e **destinazione** dello spostamento.
3. **Conferma delle restanti proposte** contrassegnate **[Proposta]**.
