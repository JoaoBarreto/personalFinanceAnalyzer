"""Contrato comum dos parsers de extratos (PRD 3.3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal, Protocol


class ParseError(ValueError):
    """Ficheiro ilegível ou com formato não reconhecido."""


@dataclass(frozen=True)
class ParsedMovement:
    data_movimento: date
    data_valor: date | None
    descricao_original: str
    montante: Decimal  # com sinal: débito < 0
    saldo_apos: Decimal | None
    ordem_no_dia: int  # 0-based, cronológica dentro do dia (derivada da cadeia de saldos)


@dataclass(frozen=True)
class ReconciliationBreak:
    index: int  # índice cronológico (0-based) da linha em que a cadeia quebra
    esperado: Decimal
    encontrado: Decimal


@dataclass
class ParsedStatement:
    moeda: str | None
    periodo_inicio: date | None
    periodo_fim: date | None
    ordem_ficheiro: Literal["asc", "desc"] | None
    saldo_inicial: Decimal | None
    saldo_final: Decimal | None
    movimentos: list[ParsedMovement] = field(default_factory=list)  # ordem cronológica
    quebras: list[ReconciliationBreak] = field(default_factory=list)

    @property
    def reconciliado(self) -> bool:
        return not self.quebras

    @property
    def diferenca(self) -> Decimal | None:
        """saldo_final − (saldo_inicial + Σ montantes); 0 quando reconcilia."""
        if self.saldo_inicial is None or self.saldo_final is None:
            return None
        return self.saldo_final - (
            self.saldo_inicial + sum((m.montante for m in self.movimentos), Decimal(0))
        )


class StatementParser(Protocol):
    bank_id: str

    def can_parse(self, content: bytes) -> float: ...  # confiança 0..1

    def parse(self, content: bytes) -> ParsedStatement: ...
