"""Tabella con modifiche manuali (SPECIFICHE_GUI.md, sezioni 3.3 e 3.4).

Il dato importato (da file o da SAP) o calcolato costituisce la "base"; le
modifiche manuali sono conservate separatamente e riapplicate ogni volta che
la base viene sostituita:

- celle modificate (origine MODIFICATO, valore importato conservato);
- righe importate rimosse: restano visibili, barrate, escluse dai calcoli e
  ripristinabili (origine RIMOSSO);
- righe inserite a mano (origine MANUALE): la rimozione le cancella davvero;
- note libere per riga.

Le righe importate sono identificate dai valori originali delle colonne
chiave; le righe manuali da un identificativo interno. Le modifiche relative
a righe importate non più presenti nella base sono "orfane".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

ORIGINE_IMPORTATO = "IMPORTATO"
ORIGINE_MODIFICATO = "MODIFICATO"
ORIGINE_MANUALE = "MANUALE"
ORIGINE_RIMOSSO = "RIMOSSO"

COL_ORIGINE = "Origine"
COL_NOTE = "Note"

_SEP_CHIAVE = "\x1f"


class ErroreModifica(Exception):
    """Modifica manuale non ammessa (messaggio in italiano per l'utente)."""


@dataclass(frozen=True)
class MetaRiga:
    """Informazioni per la visualizzazione di una riga."""
    chiave: str
    origine: str
    originali: dict[str, str] = field(default_factory=dict)   # colonna -> valore importato

    @property
    def manuale(self) -> bool:
        return self.origine == ORIGINE_MANUALE

    @property
    def rimossa(self) -> bool:
        return self.origine == ORIGINE_RIMOSSO


def _testo(valore: Any) -> str:
    if valore is None or (isinstance(valore, float) and pd.isna(valore)):
        return ""
    return str(valore)


class Tabella:
    def __init__(self, colonne: tuple[str, ...], chiave: tuple[str, ...] | None = None,
                 normalizza: dict[str, Callable[[Any], str]] | None = None,
                 valida: Callable[[dict[str, str]], list[str]] | None = None,
                 notifica: Callable[[], None] | None = None):
        self.colonne = tuple(colonne)
        self.chiave = tuple(chiave or colonne[:1])
        self._normalizza = normalizza or {}
        self._valida = valida
        self.notifica = notifica
        # se restituisce un messaggio, le modifiche manuali non sono ammesse
        self.blocco: Callable[[], str | None] | None = None
        self.versione = 0
        self._base: list[tuple[str, dict[str, str]]] = []      # (chiave, valori)
        self.modificate: dict[str, dict[str, str]] = {}
        self.rimosse: set[str] = set()
        self.aggiunte: dict[str, dict[str, str]] = {}
        self.note: dict[str, str] = {}
        self._contatore = 0

    # ------------------------------------------------------------------
    # Supporto
    # ------------------------------------------------------------------
    def _norm(self, colonna: str, valore: Any) -> str:
        fn = self._normalizza.get(colonna)
        return fn(valore) if fn else _testo(valore).strip()

    def _chiave_base(self, valori: dict[str, str]) -> str:
        return "B" + _SEP_CHIAVE + _SEP_CHIAVE.join(valori[c] for c in self.chiave)

    def _verifica_blocco(self) -> None:
        messaggio = self.blocco() if self.blocco else None
        if messaggio:
            raise ErroreModifica(messaggio)

    def _cambiato(self) -> None:
        self.versione += 1
        if self.notifica:
            self.notifica()

    def _righe(self):
        """(chiave, valori effettivi, meta) per tutte le righe, rimosse comprese."""
        for chiave, valori in self._base:
            mod = self.modificate.get(chiave, {})
            effettivi = {**valori, **mod}
            if chiave in self.rimosse:
                origine = ORIGINE_RIMOSSO
            elif mod:
                origine = ORIGINE_MODIFICATO
            else:
                origine = ORIGINE_IMPORTATO
            yield chiave, effettivi, MetaRiga(chiave, origine, {c: valori[c] for c in mod})
        for chiave, valori in self.aggiunte.items():
            yield chiave, dict(valori), MetaRiga(chiave, ORIGINE_MANUALE)

    def _valori(self, chiave: str) -> dict[str, str]:
        for k, valori, _ in self._righe():
            if k == chiave:
                return valori
        raise ErroreModifica("Riga non trovata.")

    def _controlla(self, valori: dict[str, str], esclusa: str | None) -> None:
        """Validazione di una riga nuova o modificata: chiave obbligatoria e
        univoca, più la validazione specifica della tabella."""
        errori = []
        if not any(valori[c] for c in self.chiave):
            errori.append(f"Valore obbligatorio: {' o '.join(self.chiave)}.")
        else:
            chiave_val = tuple(valori[c] for c in self.chiave)
            for k, altri, meta in self._righe():
                if k != esclusa and not meta.rimossa and tuple(altri[c] for c in self.chiave) == chiave_val:
                    errori.append(f"Valore già presente: {' / '.join(chiave_val)}.")
                    break
        if self._valida:
            errori.extend(self._valida(valori))
        if errori:
            raise ErroreModifica(" ".join(errori))

    # ------------------------------------------------------------------
    # Base (dato importato o calcolato)
    # ------------------------------------------------------------------
    def imposta_base(self, df: pd.DataFrame, conserva_modifiche: bool = True) -> None:
        mancanti = [c for c in self.colonne if c not in df.columns]
        if mancanti:
            raise KeyError(f"Colonne mancanti: {', '.join(mancanti)}.")
        base, viste = [], set()
        for record in df[list(self.colonne)].itertuples(index=False):
            valori = {c: self._norm(c, v) for c, v in zip(self.colonne, record)}
            chiave = self._chiave_base(valori)
            if chiave in viste:
                continue                                   # duplicati: vale la prima
            viste.add(chiave)
            base.append((chiave, valori))
        self._base = base
        if not conserva_modifiche:
            self.modificate.clear()
            self.rimosse.clear()
            self.aggiunte.clear()
            self.note.clear()
        self._cambiato()

    @property
    def vuota(self) -> bool:
        return not self._base and not self.aggiunte

    @property
    def righe_importate(self) -> int:
        """Righe del dato importato, indipendentemente dalle modifiche manuali."""
        return len(self._base)

    def dati_importati(self) -> pd.DataFrame:
        """Il dato importato così com'è, senza modifiche manuali."""
        return pd.DataFrame([valori for _, valori in self._base], columns=list(self.colonne), dtype=str)

    def orfane(self) -> list[str]:
        """Chiavi di modifiche, rimozioni e note su righe non più presenti."""
        presenti = {k for k, _ in self._base} | set(self.aggiunte)
        return sorted((set(self.modificate) | self.rimosse | set(self.note)) - presenti)

    def elimina_orfane(self) -> None:
        self._verifica_blocco()
        for k in self.orfane():
            self.modificate.pop(k, None)
            self.rimosse.discard(k)
            self.note.pop(k, None)
        self._cambiato()

    def conta_modifiche(self) -> int:
        return len(self.modificate) + len(self.rimosse) + len(self.aggiunte)

    # ------------------------------------------------------------------
    # Lettura
    # ------------------------------------------------------------------
    def dati(self) -> pd.DataFrame:
        """Righe effettive (modifiche applicate, rimosse escluse), per i calcoli."""
        righe = [valori for _, valori, meta in self._righe() if not meta.rimossa]
        return pd.DataFrame(righe, columns=list(self.colonne), dtype=str)

    def vista(self) -> tuple[pd.DataFrame, list[MetaRiga]]:
        """Tutte le righe (comprese le rimosse) con le colonne Origine e Note,
        e le informazioni per la visualizzazione."""
        righe, meta = [], []
        for chiave, valori, m in self._righe():
            righe.append({**valori, COL_ORIGINE: m.origine, COL_NOTE: self.note.get(chiave, "")})
            meta.append(m)
        df = pd.DataFrame(righe, columns=[*self.colonne, COL_ORIGINE, COL_NOTE], dtype=str)
        return df, meta

    # ------------------------------------------------------------------
    # Modifiche manuali
    # ------------------------------------------------------------------
    def modifica(self, chiave: str, colonna: str, valore: Any) -> None:
        self._verifica_blocco()
        if colonna not in self.colonne:
            raise ErroreModifica(f"Colonna \"{colonna}\" non modificabile.")
        if chiave in self.rimosse:
            raise ErroreModifica("Riga rimossa: ripristinarla prima di modificarla.")
        valori = self._valori(chiave)
        nuovi = {**valori, colonna: self._norm(colonna, valore)}
        if nuovi == valori:
            return
        self._controlla(nuovi, esclusa=chiave)
        if chiave in self.aggiunte:
            self.aggiunte[chiave] = nuovi
        else:
            originali = dict(next(v for k, v in self._base if k == chiave))
            diverse = {c: v for c, v in nuovi.items() if v != originali[c]}
            if diverse:
                self.modificate[chiave] = diverse
            else:
                self.modificate.pop(chiave, None)       # tornata al valore importato
        self._cambiato()

    def ripristina_cella(self, chiave: str, colonna: str) -> None:
        """Ritorno al valore importato della cella."""
        self._verifica_blocco()
        mod = self.modificate.get(chiave)
        if not mod or colonna not in mod:
            return
        originali = next(v for k, v in self._base if k == chiave)
        valori = {**originali, **{c: v for c, v in mod.items() if c != colonna}}
        self._controlla(valori, esclusa=chiave)
        del mod[colonna]
        if not mod:
            del self.modificate[chiave]
        self._cambiato()

    def aggiungi(self, valori: dict[str, Any]) -> str:
        self._verifica_blocco()
        nuovi = {c: self._norm(c, valori.get(c)) for c in self.colonne}
        self._controlla(nuovi, esclusa=None)
        self._contatore += 1
        chiave = f"M{_SEP_CHIAVE}{self._contatore}"
        self.aggiunte[chiave] = nuovi
        self._cambiato()
        return chiave

    def rimuovi(self, chiave: str) -> None:
        self._verifica_blocco()
        if chiave in self.aggiunte:
            del self.aggiunte[chiave]
            self.note.pop(chiave, None)
        elif any(k == chiave for k, _ in self._base):
            self.rimosse.add(chiave)
        else:
            raise ErroreModifica("Riga non trovata.")
        self._cambiato()

    def ripristina(self, chiave: str) -> None:
        """Ripristino di una riga importata rimossa."""
        self._verifica_blocco()
        if chiave not in self.rimosse:
            return
        self._controlla(self._valori(chiave), esclusa=chiave)
        self.rimosse.discard(chiave)
        self._cambiato()

    def imposta_nota(self, chiave: str, testo: str) -> None:
        self._verifica_blocco()
        testo = _testo(testo).strip()
        if testo:
            self.note[chiave] = testo
        else:
            self.note.pop(chiave, None)
        self._cambiato()

    # ------------------------------------------------------------------
    # Salvataggio
    # ------------------------------------------------------------------
    def serializza(self) -> dict:
        return {
            "base": [valori for _, valori in self._base],
            "modificate": self.modificate,
            "rimosse": sorted(self.rimosse),
            "aggiunte": self.aggiunte,
            "note": self.note,
            "contatore": self._contatore,
        }

    def ripristina_da(self, dati: dict) -> None:
        self._base = [(self._chiave_base(v), {c: v.get(c, "") for c in self.colonne})
                      for v in dati.get("base", [])]
        self.modificate = {k: dict(v) for k, v in dati.get("modificate", {}).items()}
        self.rimosse = set(dati.get("rimosse", []))
        self.aggiunte = {k: dict(v) for k, v in dati.get("aggiunte", {}).items()}
        self.note = dict(dati.get("note", {}))
        self._contatore = int(dati.get("contatore", 0))
        self.versione += 1
