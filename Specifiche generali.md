# Indicazioni generali

> **Destinatario:** Claude Code.
> Il documento descrive il programma da implementare, fornisce indicazioni sulla finalità del programma e sulla interfacccia che si desidera creare.

---

## 1. Obiettivo
Il programma deve supportare nella modifica di stringhe con il significato di sedi tecniche di anagrafica di impianto mediante l'applicazione di nuove regole. Al termine del processo si devono ottenere dei file che permettono il caricamento in SAP per effettuare modifiche/cancellazioni/creazioni di sedi tecniche al fine di ottenere una struttura coerente con le nuove regole.

# Interfaccia GUI
 
L'interfaccia deve prevedere una videata in cui è presente un Tab Control, contenente le seguenti schede:
## Tab Control
**New** Deve contenere una tabella con due colonne nominate "Sede tecnica" e "Descrizione". Deve contenere un pulsante che permetta il caricamento dei dati da un file excel.
Per il caricamento del file dovrà essere verificata la presenza di due colonne con intestazione. La prima colonna contiene i dati relativi alla lista di sedi tecniche mentre la seconda colonna le relative descrizioni.
Se il controllo non va a buon fine si deve interrompere il caricamento e mostrare un messaggio di errore. 
**Actual** Simile alla tabella New deve contenere i dati prelevati da SAP tramite l'esecuzione di una specifica transazione di cui le specifiche saranno fornite in un secondo momento.
**No_Wo** Deve contenere due colonne una con intestazione "Work Order" e l'altra con intestazione "Notification". Deve contenere un pulsante con la dicitura "Aggiorna" che avvierà la comunicazione con il sistema SAP per ricavare eventuali Work Order o Notification da inserire nella lista, ed un pulsante con la dicitura "Esporta" che deve permettere di esportare il contenuto della tabella in un file excel.
**FL da creare** Deve contenere una tabella contenente quattro colonne: "Sede tecnica" contenente la lista delle sedi tecniche presente nella tab "actual" e la colonna "Codice_out", "Nuove sedi tecniche" ed "Esito" come definito nel file @SPECIFICHE_CONVERSIONE_SEDI.md 
**Check Parent** Deve contenere una tabella con due colonne: una colonna denominata "Nuove sedi tecniche" in cui devono essere presenti le righe della tabella della tb "FL da creare" combinate nel seguente modo: Le righe della colonna "Sede tecnica" se nella colonna "Nuove sedi tecniche" non è presente nessun valore oppure il valore presente nella colonna "Nuove sedi tecniche"; ed una colonna denominata "Check".
Nella tab deve essere presente un pulsante con la dicitura "Check" ed un pulsante con la dicitura "Esporta" che deve permettere di esportare il contenuto della tabella in un file excel.
Il pulsante "Check" permette di avviare la verifica della gerarchia dei dati presenti nella tabella. I dati presenti nella tabella sono rappresentati in modo gerarchico e per ogni elemento presente nella tabella deve essere verificata la presenza del genitore secondo questa regola: Ad ogni elemento deve essere assegnato un valore che ne esprime la lunghezza. Questo valore è ricavabile contando le occorrenze del carattere "-" presente nella stringa e sommando 1.
Ad esempio:
sede tecnica `ITE-OT0B-1E-01-B1-BM` lunghezza = 6
sede tecnica `ITE-OT0B-1E-01-B1` lunghezza = 5
sede tecnica `ITE-OT0B-1E-01` lunghezza = 4
sede tecnica `ITE-OT0B-1E` lunghezza = 3
sede tecnica `ITE-OT0B` lunghezza = 2
sede tecnica `ITE` lunghezza = 1

per l'elemento di lunghezza 6 deve essere verificata l'esistenza nella tabella dell'elemento di lugnhezza 5, per l'elemento 5 la presenza dell'elemento 4 e così via fino ad arrivare all'elemento 1 (la radice della gerarchia). Gli elementi che non possiedono un parent devono essere segnalati nella colonna "Check" della tabella con il testo "Parent NOK" contenuto nelle righe corrispondenti deve essere di colore rosso.
Prima di avviare il controllo per la presenza dei parent deve essere verificato che la tabella non contenga valori duplicati, se presenti vanno segnalati nella rispettiva colonna "Check" con il testo "Valore duplicato" contenuto nelle righe corrispondenti deve essere di colore rosso.
**Check New**
**Check Actual**

### Menu contestuale per le tabelle
Ogni tabella contenuta nei tab control deve avere la possibilità di attivare un menù contestuale con cui è possibile:
- copiare il contenuto dell'intera tabella nella clipboard
- copiare il contenuto della singola riga in cui si trova posizionato il mouse

### Aggiornamento delle tabelle.
ogni tabella deve prevedere la possibilità di insierire/rimuovere delle righe.
La modifiche devono prevedere l'aggiornamento dei dati
