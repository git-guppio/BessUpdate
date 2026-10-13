"""Prova delle estrazioni SAP sul sistema reale.

Uso (con SAP GUI aperto e login in italiano):
    python prova_sap.py USE-USS5
    python prova_sap.py USE-USS5 --sedi USE-USS5-1A-CS USE-USS5-00-OC

Esegue IH06 sull'impianto, poi IW39 e IW29 sulle Sedi indicate (oppure sulle
prime 20 Sedi estratte) e salva i risultati in prova_sap.xlsx.
"""
import argparse
import sys

import pandas as pd

from conversione_sedi.sap import (
    ErroreSAP, connetti_sessione, estrai_avvisi_iw29, estrai_ordini_iw39, estrai_sedi_ih06,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prova delle estrazioni SAP.")
    parser.add_argument("impianto", help="impianto, es. USE-USS5")
    parser.add_argument("--sedi", nargs="*", help="Sedi tecniche per IW39/IW29")
    parser.add_argument("-o", "--output", default="prova_sap.xlsx")
    args = parser.parse_args()

    try:
        sessione = connetti_sessione()
        print(f"IH06 su {args.impianto}* ...")
        sedi = estrai_sedi_ih06(sessione, args.impianto)
        print(f"  {len(sedi)} Sedi tecniche")

        elenco = args.sedi or sedi["Sede tecnica"].head(20).tolist()
        print(f"IW39 su {len(elenco)} Sedi ...")
        ordini = estrai_ordini_iw39(sessione, elenco)
        print(f"  {len(ordini)} Work Order")
        print(f"IW29 su {len(elenco)} Sedi ...")
        avvisi = estrai_avvisi_iw29(sessione, elenco)
        print(f"  {len(avvisi)} Notification")
    except ErroreSAP as e:
        print(f"ERRORE: {e}", file=sys.stderr)
        return 1

    with pd.ExcelWriter(args.output) as w:
        sedi.to_excel(w, sheet_name="IH06", index=False)
        ordini.to_excel(w, sheet_name="IW39", index=False)
        avvisi.to_excel(w, sheet_name="IW29", index=False)
    print(f"Risultati salvati in {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
