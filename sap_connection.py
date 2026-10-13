import win32com.client
from typing import Optional

class SAPGuiConnection:
    """
    Classe per gestire la connessione con SAP GUI utilizzando win32com
    """
    
    def __init__(self):
        """
        Inizializza gli attributi della connessione
        """
        self.SapGuiAuto: Optional[object] = None
        self.application: Optional[object] = None
        self.connection: Optional[object] = None
        self.session: Optional[object] = None

    def connect(self) -> bool:
        """
        Stabilisce una connessione con SAP GUI
        
        Returns:
            bool: True se la connessione è stabilita con successo, False altrimenti
        """
        try:
            # Stabilisco una connessione con SAP
            self.SapGuiAuto = win32com.client.GetObject('SAPGUI')
            if not self.SapGuiAuto:
                print("Errore: Impossibile ottenere l'oggetto SAPGUI")
                return False

            self.application = self.SapGuiAuto.GetScriptingEngine
            if not self.application:
                print("Errore: Impossibile ottenere Scripting Engine")
                return False

            self.connection = self.application.Children(0)
            if not self.connection:
                print("Errore: Impossibile ottenere la connessione")
                return False

            self.session = self.connection.Children(0)
            if not self.session:
                print("Errore: Impossibile ottenere la sessione")
                return False

            print("Connessione SAP stabilita con successo")
            return True

        except Exception as e:
            print(f"Errore durante la connessione a SAP: {str(e)}")
            self.disconnect()
            return False

    def disconnect(self) -> None:
        """
        Chiude la connessione SAP e rilascia le risorse
        """
        try:
            # Rilascio delle risorse in ordine inverso
            self.session = None
            self.connection = None
            self.application = None
            self.SapGuiAuto = None
            print("Disconnessione da SAP completata")
        except Exception as e:
            print(f"Errore durante la disconnessione: {str(e)}")

    def is_connected(self) -> bool:
        """
        Verifica se la connessione è attiva
        
        Returns:
            bool: True se la connessione è attiva, False altrimenti
        """
        return all([self.SapGuiAuto, self.application, self.connection, self.session])

    def get_session(self) -> Optional[object]:
        """
        Restituisce l'oggetto sessione se la connessione è attiva
        
        Returns:
            object: Oggetto sessione SAP o None se non connesso
        """
        if self.is_connected():
            return self.session
        return None

    def __enter__(self):
        """
        Permette l'utilizzo del context manager (with statement)
        """
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Chiude automaticamente la connessione alla fine del blocco with
        """
        self.disconnect()



""" 

def main():
    # Esempio di utilizzo della classe
    try:
        # Metodo 1: Utilizzo tradizionale
        sap = SAPGuiConnection()
        if sap.connect():
            # Ottieni la sessione per eseguire operazioni
            session = sap.get_session()
            if session:
                # Esempio di utilizzo della sessione
                print("Connessione attiva, pronta per le operazioni")
                # Qui puoi inserire le tue operazioni SAP
            
            # Chiudi la connessione
            sap.disconnect()

        # Metodo 2: Utilizzo con context manager
        with SAPGuiConnection() as sap:
            if sap.is_connected():
                session = sap.get_session()
                if session:
                    print("Connessione attiva nel context manager")
                    # Qui puoi inserire le tue operazioni SAP

    except Exception as e:
        print(f"Errore generale: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
    
"""