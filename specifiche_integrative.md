

---

## 1. Gestione delle sedi tecniche

Avvisi e ordini di lavoro vanno chiusi **solo quando una sede tecnica viene eliminata**. La sola modifica della sola etichetta mantiene invariato l'ID interno SAP e consente l'aggiornamento automatico dei riferimenti.

- **Modifica dell'etichetta.** Ogni sede tecnica è composta da un ID interno SAP e da un'etichetta esterna visibile agli utenti. Poiché la modifica dell'etichetta non altera l'ID interno, avvisi e ordini continuano a riferirsi alla stessa sede e acquisiscono automaticamente la nuova etichetta.
- **Eliminazione della sede.** L'eliminazione e la successiva ricreazione di una sede tecnica comportano la generazione di un nuovo ID interno SAP. Gli avvisi e gli ordini associati devono quindi essere chiusi prima della ricreazione, poiché non vengono ereditati dalla nuova sede.
- **Ambito della chiusura.** È stato confermato che le *work order e notification* da chiudere riguardano esclusivamente le sedi destinate all'eliminazione; le sedi semplicemente modificate non richiedono alcuna chiusura.

_questa informazione impatta le funzioni contenute nella barra laterale alla posizione numero 7 No Wo. Dovranno essere prese in considerazione solamente le sedi tecniche contrassegnate come da eliminare_
---

## 2. Sequenza di creazione e modifica

La sequenza degli step dipende dalla gerarchia SAP: un elemento può essere creato solo se il relativo genitore esiste già.

- **Creazione iniziale.** Nel primo step vengono creati gli elementi mancanti il cui genitore è già presente nella struttura attuale.
- **Creazione successiva (parte due).** Se il genitore non esiste nella struttura attuale ma sarà reso disponibile da una modifica, l'elemento figlio deve essere collocato nello step successivo. La valutazione va effettuata per ciascuna sede tecnica.
- **Esempio gerarchico.** Se, a esempio, in una lista di sedi tecniche non è presente una sede tecnica di 4 livello non si potrà procedere con la creazione dei figli al 5 livello se prima non si sarà provveduto alla creazione del 4 che potrebbe essere anche prodotto dalla modifica/ridenominazione di una sede tecnica esistente; l'ordine inverso avrebbe generato errori per l'assenza del genitore.
- **Regola di controllo.** 
  - genitore già esistente → l'elemento può essere creato;
  - genitore disponibile solo dopo una modifica → la creazione va posticipata.

---

## 3.  "New Superior" delle rimozioni

Durante l'applicazione della CC04 per la rimozione delle sedi tecniche si adotta normalmente il **primo livello come parent** (i primi due caratteri + "A"); non è necessario indicare il parent esatto.

- **Parent di migrazione.** Si raccomanda di impostare sempre il primo livello come parent nello spostamento di porzioni dell'anagrafica, trattandosi di un livello sicuramente esistente. L'utilizzo della struttura completa potrebbe far fallire la migrazione in caso di assenza di un parent intermedio.

- **Propagazione ai figli.** La CC04 massiva consente di propagare la modifica ai figli, ma non elimina la necessità di ordinare correttamente creazioni, modifiche ed eliminazioni: una modifica può infatti trasformare i codici dei figli, rendendoli non più riconoscibili nella lista originaria.

---

## 4. Eliminazioni e trasformazione dei codici

Le eliminazioni devono essere collocate tenendo conto delle modifiche, poiché queste ultime possono trasformare i codici e rendere indisponibili gli identificativi necessari alla cancellazione.

- **Rischio di eliminazione.** Un'eliminazione anticipata o tardiva può generare problemi quando alcune cancellazioni dipendono da modifiche precedenti: la propagazione ai figli può alterarne i codici, con conseguente perdita della corrispondenza con la lista iniziale.
- **Transcodifica.** Qualora i codici cambino prima della cancellazione, risulterebbe necessario transcodificare gli elementi interessati per identificarli correttamente. La sequenza degli step deve pertanto preservare i codici fino al momento opportuno.

---

---

## Attività di completamento

| # | Attività | Descrizione |
|---|---|---|---|
| 1 | **Sequenza di migrazione** | Aggiornare la logica degli step: creare prima gli elementi con genitore già esistente e rinviare allo step successivo quelli privi di genitore, verificando la gerarchia per ogni sede tecnica.
| 2 | **Ordine di esecuzione** | Correggere l'ordine delle operazioni, gestendo gli elementi da creare necessari alla gerarchia prima delle modifiche o eliminazioni che potrebbero generarne nuovi codici.
