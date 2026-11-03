"""Deduplicação por multiset (PRD 4.1). Função pura, sem BD.

Chave base: (data_movimento, montante) dentro de uma conta. Para cada chave o ficheiro tem n linhas e a BD m.
Refinamento por saldo só quando ambos os lados têm `saldo_apos`; se um lado não tem, cai na chave base.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import NamedTuple


class Row(NamedTuple):
    data_movimento: date
    montante: Decimal
    saldo_apos: Decimal | None


@dataclass
class DedupResult:
    novos: list[int] = field(default_factory=list)  # índices em `ficheiro` a inserir
    duplicados: list[int] = field(default_factory=list)  # já existem na BD
    possiveis_duplicados: list[int] = field(default_factory=list)  # ambíguos: o utilizador decide


def deduplicate(ficheiro: list[Row], existentes: list[Row]) -> DedupResult:
    by_key: dict[tuple[date, Decimal], list[int]] = {}
    for i, r in enumerate(ficheiro):
        by_key.setdefault((r.data_movimento, r.montante), []).append(i)
    db_by_key: dict[tuple[date, Decimal], list[Row]] = {}
    for r in existentes:
        db_by_key.setdefault((r.data_movimento, r.montante), []).append(r)

    res = DedupResult()
    for key, idxs in by_key.items():
        pool = list(db_by_key.get(key, []))
        pending: list[int] = []
        # A) saldo igual em ambos os lados
        for i in idxs:
            s = ficheiro[i].saldo_apos
            hit = next((j for j, e in enumerate(pool) if s is not None and e.saldo_apos == s), None)
            if hit is None:
                pending.append(i)
            else:
                pool.pop(hit)
                res.duplicados.append(i)
        # B) fallback: um dos lados sem saldo -> chave base
        still: list[int] = []
        for i in pending:
            hit = next(
                (j for j, e in enumerate(pool) if ficheiro[i].saldo_apos is None or e.saldo_apos is None),
                None,
            )
            if hit is None:
                still.append(i)
            else:
                pool.pop(hit)
                res.duplicados.append(i)
        # C) sobras: se ainda há linhas da BD com saldo diferente, é ambíguo; senão é novo
        for i in still:
            if pool:
                pool.pop(0)
                res.possiveis_duplicados.append(i)
            else:
                res.novos.append(i)
    for lst in (res.novos, res.duplicados, res.possiveis_duplicados):
        lst.sort()
    return res
