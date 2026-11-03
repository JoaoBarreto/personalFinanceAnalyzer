"""Saldo da conta numa data, a partir da coluna de saldo dos movimentos (cadeia de saldos).

Calcula-se por conta e soma-se sobre o âmbito, porque o filtro de titular pode abranger várias contas.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from ..models import Movimento


def _last_saldo(db: Session, scope, upto: date, inclusive: bool) -> dict[int, Decimal]:
    cond = Movimento.data_movimento <= upto if inclusive else Movimento.data_movimento < upto
    q = (
        select(Movimento.conta_id, Movimento.saldo_apos)
        .where(cond, Movimento.saldo_apos.is_not(None), *scope)
        # DISTINCT ON exige que o ORDER BY comece por conta_id
        .order_by(
            Movimento.conta_id,
            Movimento.data_movimento.desc(),
            Movimento.ordem_no_dia.desc(),
            Movimento.id.desc(),
        )
        .ext(distinct_on(Movimento.conta_id))
    )
    return {c: s for c, s in db.execute(q)}


def saldo_em(db: Session, scope, d: date) -> Decimal | None:
    """Saldo no fim do dia `d` (último saldo_apos até essa data); None se não houver movimentos até lá."""
    vals = _last_saldo(db, scope, d, True)
    return sum(vals.values(), Decimal(0)) if vals else None


def saldo_abertura(db: Session, scope, d0: date, d1: date) -> Decimal | None:
    """Saldo à entrada do período [d0, d1].

    Por conta: o último saldo antes de d0; se a conta não tem movimentos anteriores, a abertura do seu 1.º
    movimento no período (saldo_apos − montante); se não tem nenhuma das duas, não contribui.
    """
    before = _last_saldo(db, scope, d0, False)
    q = (
        select(Movimento.conta_id, Movimento.saldo_apos - Movimento.montante)
        .where(Movimento.data_movimento.between(d0, d1), Movimento.saldo_apos.is_not(None), *scope)
        .order_by(Movimento.conta_id, Movimento.data_movimento, Movimento.ordem_no_dia, Movimento.id)
        .ext(distinct_on(Movimento.conta_id))
    )
    merged = {**{c: s for c, s in db.execute(q)}, **before}  # o saldo anterior tem prioridade
    return sum(merged.values(), Decimal(0)) if merged else None
