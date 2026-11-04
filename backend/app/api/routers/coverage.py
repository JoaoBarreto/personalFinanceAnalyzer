"""Cobertura dos dados por conta e deteção de buracos na cadeia de saldos."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...deps import Auth, get_db, require_auth
from ...models import Conta, Movimento

router = APIRouter(prefix="/api/coverage", tags=["coverage"])


def gaps(db: Session, conta_id: int) -> list[dict]:
    """Buraco = linha em que `saldo_anterior + montante ≠ saldo_apos` (faltam movimentos entre as duas)."""
    order = (Movimento.data_movimento, Movimento.ordem_no_dia, Movimento.id)
    sub = (
        select(
            Movimento.data_movimento.label("data"),
            Movimento.montante,
            Movimento.saldo_apos,
            func.lag(Movimento.saldo_apos).over(order_by=order).label("prev_saldo"),
            func.lag(Movimento.data_movimento).over(order_by=order).label("prev_data"),
        )
        .where(Movimento.conta_id == conta_id)
        .subquery()
    )
    rows = db.execute(
        select(sub.c.prev_data, sub.c.data, sub.c.saldo_apos - (sub.c.prev_saldo + sub.c.montante))
        .where(
            sub.c.prev_saldo.is_not(None),
            sub.c.saldo_apos.is_not(None),
            sub.c.prev_saldo + sub.c.montante != sub.c.saldo_apos,
        )
        .order_by(sub.c.data)
    ).all()
    return [{"de": de, "ate": ate, "diferenca": str(dif)} for de, ate, dif in rows]


@router.get("")
def coverage(auth: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    out = []
    contas = select(Conta).where(Conta.arquivada.is_(False), Conta.dono_id == auth.utilizador.id)
    for c in db.scalars(contas.order_by(Conta.id)):
        first, last, n = db.execute(
            select(
                func.min(Movimento.data_movimento), func.max(Movimento.data_movimento), func.count()
            ).where(Movimento.conta_id == c.id)
        ).one()
        falhas = gaps(db, c.id) if n else []
        out.append(
            {
                "conta_id": c.id,
                "nome": c.nome,
                "primeiro": first,
                "ultimo": last,
                "n_movimentos": n,
                "falhas": falhas,
                "ok": not falhas,
            }
        )
    return out
