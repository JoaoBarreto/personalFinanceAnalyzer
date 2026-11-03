"""Reconciliação por cadeia de saldos e deteção da ordem do ficheiro (PRD 4.3)."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from .base import ReconciliationBreak

Row = tuple[Decimal, Decimal]  # (montante, saldo_apos), pela ordem do ficheiro


def _breaks(rows: list[Row]) -> list[ReconciliationBreak]:
    """Quebras da cadeia `saldo_anterior + montante = saldo_apos` para linhas já em ordem cronológica."""
    out = []
    for i in range(1, len(rows)):
        esperado = rows[i - 1][1] + rows[i][0]
        if esperado != rows[i][1]:
            out.append(ReconciliationBreak(i, esperado, rows[i][1]))
    return out


def detect_order(rows: list[Row]) -> tuple[Literal["asc", "desc"], bool]:
    """Devolve (ordem, ambiguo). A ordem é aquela em que a cadeia tem menos quebras.

    Com <2 linhas, ou empate, assume 'asc' e marca como ambíguo.
    """
    if len(rows) < 2:
        return "asc", True
    asc = len(_breaks(rows))
    desc = len(_breaks(rows[::-1]))
    if asc == desc:
        return "asc", True
    return ("asc", False) if asc < desc else ("desc", False)


def chronological_breaks(rows_chrono: list[Row]) -> list[ReconciliationBreak]:
    return _breaks(rows_chrono)
