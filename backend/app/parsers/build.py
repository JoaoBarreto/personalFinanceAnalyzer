"""Construção do ParsedStatement a partir das linhas já validadas (partilhada pelos parsers)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from .base import ParsedMovement, ParsedStatement
from .reconcile import chronological_breaks, detect_order

RawRow = tuple[date, date | None, str, Decimal, Decimal]  # (data_mov, data_valor, descrição, montante, saldo)


def build_statement(
    raw: list[RawRow], moeda: str | None, periodo_inicio: date | None, periodo_fim: date | None
) -> ParsedStatement:
    """`raw` na ordem do ficheiro. Deteta a ordem pela cadeia de saldos, põe em ordem cronológica e reconcilia."""
    ordem, ambigua = detect_order([(r[3], r[4]) for r in raw])
    chrono = raw if ordem == "asc" else raw[::-1]

    movimentos: list[ParsedMovement] = []
    counter: dict[date, int] = {}
    for dm, dv, desc, montante, saldo in chrono:
        n = counter.get(dm, 0)
        counter[dm] = n + 1
        movimentos.append(ParsedMovement(dm, dv, desc, montante, saldo, n))

    return ParsedStatement(
        moeda=moeda,
        periodo_inicio=periodo_inicio or movimentos[0].data_movimento,
        periodo_fim=periodo_fim or movimentos[-1].data_movimento,
        ordem_ficheiro=ordem,
        ordem_ambigua=ambigua,
        saldo_inicial=chrono[0][4] - chrono[0][3],
        saldo_final=chrono[-1][4],
        movimentos=movimentos,
        quebras=chronological_breaks([(r[3], r[4]) for r in chrono]),
    )
