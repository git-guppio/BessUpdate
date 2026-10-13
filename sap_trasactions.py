####################################
# Transazione IW39 per estrarre OdM 
#########################################
    session.findById("wnd[0]").resizeWorkingPane(173, 55, False)
    session.findById("wnd[0]/usr/cntlIMAGE_CONTAINER/shellcont/shell/shellcont[0]/shell").expandNode("F00004")
    session.findById("wnd[0]/usr/cntlIMAGE_CONTAINER/shellcont/shell/shellcont[0]/shell").topNode = "Favo"
    session.findById("wnd[0]/tbar[0]/okcd").text = "/niw39"
    session.findById("wnd[0]").sendVKey(0)
# rimuovo flag su chiusi
    session.findById("wnd[0]/usr/chkDY_OFN").selected = True
    session.findById("wnd[0]/usr/chkDY_IAR").selected = True
    session.findById("wnd[0]/usr/chkDY_MAB").selected = False
    session.findById("wnd[0]/usr/chkDY_HIS").selected = True
    session.findById("wnd[0]/usr/chkDY_HIS").setFocus()
# inserisco dagli appunti la lista delle sedi tecniche
    session.findById("wnd[0]/usr/btn%_STRNO_%_APP_%-VALU_PUSH").press()
    session.findById("wnd[1]/tbar[0]/btn[24]").press()
    session.findById("wnd[1]/tbar[0]/btn[8]").press()
# tolgo date

    session.findById("wnd[0]/usr/ctxtDATUV").text = ""
    session.findById("wnd[0]/usr/ctxtDATUB").text = ""
    session.findById("wnd[0]/usr/ctxtDATUB").setFocus()
    session.findById("wnd[0]/usr/ctxtDATUB").caretPosition = 0
    session.findById("wnd[0]").sendVKey(0)
# seleziono un layout
    session.findById("wnd[0]/usr/ctxtVARIANT").text = "/KPIODMPOOL"
    session.findById("wnd[0]/usr/ctxtVARIANT").setFocus()
    session.findById("wnd[0]/usr/ctxtVARIANT").caretPosition = 11
    session.findById("wnd[0]").sendVKey(0)
# avvio trasnazione
    session.findById("wnd[0]/tbar[1]/btn[8]").press()
# verifico se ci sono errori analizzando il testo nella status bar
# se ad esempio compare "Non sono stati selezionati oggetti" allora non ci sono ordini da estrarre e quindi esco dalla transazione

# se invece non ci sono messaggi nella status bar allora verifico il nome della finestra per capire se si tratta di un singolo ordine oppure di una lista di ordini
# se contiene <Visualizzare ordine> allora si tratta di un singolo ordine.
# copio codice adm e descrizione

    OdM = session.findById("wnd[0]/usr/subSCREEN_1:SAPLIQS0:1050/txtVIQMEL-QMNUM").txt
    testoBreve = session.findById("wnd[0]/usr/subSCREEN_1:SAPLIQS0:1050/subNOTIF_TYPE:SAPLIQS0:1051/txtVIQMEL-QMTXT").txt

# se il nome della finsetra contiene <Visualizzare ordini> allora contiene una lista allora esporto nella clipboards
    session.findById("wnd[0]/mbar/menu[0]/menu[11]/menu[2]").select()
    session.findById("wnd[1]/usr/subSUBSCREEN_STEPLOOP:SAPLSPO5:0150/sub:SAPLSPO5:0150/radSPOPLI-SELFLAG[4,0]").select()
    session.findById("wnd[1]/usr/subSUBSCREEN_STEPLOOP:SAPLSPO5:0150/sub:SAPLSPO5:0150/radSPOPLI-SELFLAG[4,0]").setFocus()
    session.findById("wnd[1]/tbar[0]/btn[0]").press()
# Restuituisco l'esito della transazione come tuple di valori (OdM, testoBreve).    
# Nel caso di lista di ordini il contenuto è presente nella clipboard e deve quindi essere riportato in una lista di tuple di valori (OdM, testoBreve) prima di restituire l'esito della transazione. In questo caso la funzione restituirà una lista di tuple di valori (OdM, testoBreve) e non una singola tupla di valori (OdM, testoBreve).
    return OdM, testoBreve



##################################
# Transazione IW29 per estrarre AdM
####################################
    session.findById("wnd[0]/usr/cntlIMAGE_CONTAINER/shellcont/shell/shellcont[0]/shell").expandNode("F00003")
    session.findById("wnd[0]/usr/cntlIMAGE_CONTAINER/shellcont/shell/shellcont[0]/shell").topNode = "Favo"
    session.findById("wnd[0]/tbar[0]/okcd").text = "/niw29"
    session.findById("wnd[0]").sendVKey(0)
# Tolgo il flag a chiusi

    session.findById("wnd[0]/usr/chkDY_OFN").selected = True
    session.findById("wnd[0]/usr/chkDY_RST").selected = True
    session.findById("wnd[0]/usr/chkDY_IAR").selected = True
    session.findById("wnd[0]/usr/chkDY_MAB").selected = False
#inserisco lista sedi tecniche dalla clipboard
    session.findById("wnd[0]/usr/chkDY_IAR").setFocus()
    session.findById("wnd[0]/usr/btn%_STRNO_%_APP_%-VALU_PUSH").press()
    session.findById("wnd[1]/tbar[0]/btn[24]").press()
    session.findById("wnd[1]/tbar[0]/btn[8]").press()
# elimino date
    session.findById("wnd[0]/usr/ctxtDATUV").text = ""
    session.findById("wnd[0]/usr/ctxtDATUB").text = ""
    session.findById("wnd[0]/usr/ctxtDATUB").setFocus()
    session.findById("wnd[0]/usr/ctxtDATUB").caretPosition = 0
    session.findById("wnd[0]").sendVKey(0)
# seleziono un layout
    session.findById("wnd[0]/usr/ctxtVARIANT").text = "KPIADMPOOL"
    session.findById("wnd[0]/usr/ctxtVARIANT").setFocus()
    session.findById("wnd[0]/usr/ctxtVARIANT").caretPosition = 10
# avvio transazione
    session.findById("wnd[0]/tbar[1]/btn[8]").press()
# verifico se ci sono errori analizzando il testo nella status bar
# se ad esempio compare "Non sono stati selezionati oggetti" allora non ci sono avvisi da estrarre e quindi esco dalla transazione

# se invece non ci sono messaggi nella status bar allora verifico il nome della finestra per capire se si tratta di un singolo avviso oppure di una lista di avvisi
# se contiene <Visualizzare avviso> allora si tratta di un singolo avviso.
# copio codice adm e descrizione

    AdM = session.findById("wnd[0]/usr/subSCREEN_1:SAPLIQS0:1050/txtVIQMEL-QMNUM").txt
    testoBreve = session.findById("wnd[0]/usr/subSCREEN_1:SAPLIQS0:1050/subNOTIF_TYPE:SAPLIQS0:1051/txtVIQMEL-QMTXT").txt

# se il nome della finsetra contiene <Visualizzare avvisi> allora contiene una lista allora esporto nella clipboards
    session.findById("wnd[0]/mbar/menu[0]/menu[11]/menu[2]").select()
    session.findById("wnd[1]/usr/subSUBSCREEN_STEPLOOP:SAPLSPO5:0150/sub:SAPLSPO5:0150/radSPOPLI-SELFLAG[4,0]").select()
    session.findById("wnd[1]/usr/subSUBSCREEN_STEPLOOP:SAPLSPO5:0150/sub:SAPLSPO5:0150/radSPOPLI-SELFLAG[4,0]").setFocus()
    session.findById("wnd[1]/tbar[0]/btn[0]").press()
# Restuituisco l'esito della transazione come tuple di valori (AdM, testoBreve).    
# Nel caso di lista di avvisi il contenuto è presente nella clipboard e deve quindi essere riportato in una lista di tuple di valori (AdM, testoBreve) prima di restituire l'esito della transazione. In questo caso la funzione restituirà una lista di tuple di valori (AdM, testoBreve) e non una singola tupla di valori (AdM, testoBreve).
    return AdM, testoBreve


##################################
# Transazione IH06 per estrarre sedi tecniche
####################################
    session.findById("wnd[0]").resizeWorkingPane(173, 44, False)
    session.findById("wnd[0]").resizeWorkingPane(173, 44, False)
    session.findById("wnd[0]/usr/cntlIMAGE_CONTAINER/shellcont/shell/shellcont[0]/shell").unselectAll()
    session.findById("wnd[0]/tbar[0]/okcd").text = "/nih06"
    session.findById("wnd[0]").sendVKey(0)
    session.findById("wnd[0]/usr/ctxtSTRNO-LOW").text = "USE-USS5*"
    session.findById("wnd[0]/usr/ctxtVARIANT").text = "FL_BESS_MIG"
    session.findById("wnd[0]/usr/ctxtVARIANT").setFocus()
    session.findById("wnd[0]/usr/ctxtVARIANT").caretPosition = 11
    session.findById("wnd[0]/tbar[1]/btn[8]").press()
    session.findById("wnd[0]/mbar/menu[0]/menu[10]/menu[2]").select()
    session.findById("wnd[1]/usr/subSUBSCREEN_STEPLOOP:SAPLSPO5:0150/sub:SAPLSPO5:0150/radSPOPLI-SELFLAG[4,0]").select()
    session.findById("wnd[1]/usr/subSUBSCREEN_STEPLOOP:SAPLSPO5:0150/sub:SAPLSPO5:0150/radSPOPLI-SELFLAG[4,0]").setFocus()
    session.findById("wnd[1]/tbar[0]/btn[0]").press()
