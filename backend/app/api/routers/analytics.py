"""Agregações do dashboard (PRD 3.9), em SQL.

Convenções: despesa = montante < 0, receita = montante > 0 (reembolsos só na Fase 2). Movimentos cuja categoria
é do tipo `transferencia` ficam fora dos totais salvo `incluir_transferencias=true`. Dinheiro sempre em string.
"""

import calendar
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from ...deps import Auth, get_db, require_auth
from ...models import Categoria, Movimento

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

ZERO = Decimal(0)
DESPESA = func.coalesce(func.sum(case((Movimento.montante < 0, -Movimento.montante), else_=0)), 0)
RECEITA = func.coalesce(func.sum(case((Movimento.montante > 0, Movimento.montante), else_=0)), 0)


def _filters(conta_id, incluir_transferencias, d0=None, d1=None):
    conds = []
    if conta_id is not None:
        conds.append(Movimento.conta_id == conta_id)
    if d0:
        conds.append(Movimento.data_movimento >= d0)
    if d1:
        conds.append(Movimento.data_movimento <= d1)
    if not incluir_transferencias:
        conds.append(or_(Categoria.tipo.is_(None), Categoria.tipo != "transferencia"))
    return conds


def _base(*cols):
    return select(*cols).select_from(Movimento).outerjoin(Categoria, Categoria.id == Movimento.categoria_id)


def _totals(db: Session, conta_id, incl, d0, d1) -> tuple[Decimal, Decimal]:
    r = db.execute(_base(DESPESA, RECEITA).where(*_filters(conta_id, incl, d0, d1))).one()
    return Decimal(r[0]), Decimal(r[1])


def _s(x: Decimal) -> str:
    return str(x.quantize(Decimal("0.01")))


def _pct(num: Decimal, den: Decimal) -> str | None:
    return None if den == 0 else str((num / den * 100).quantize(Decimal("0.01")))


def _period(db: Session, d0: date | None, d1: date | None) -> tuple[date, date]:
    if d0 and d1:
        return d0, d1
    last = db.scalar(select(func.max(Movimento.data_movimento))) or date.today()
    return d0 or last.replace(day=1), d1 or last.replace(day=calendar.monthrange(last.year, last.month)[1])


def _month_start(d: date, back: int) -> date:
    m = d.year * 12 + d.month - 1 - back
    return date(m // 12, m % 12 + 1, 1)


def _previous(d0: date, d1: date) -> tuple[date, date]:
    full_month = d0.day == 1 and d1 == d0.replace(day=calendar.monthrange(d0.year, d0.month)[1])
    if full_month:
        p0 = _month_start(d0, 1)
        return p0, d0 - timedelta(days=1)
    n = (d1 - d0).days + 1
    return d0 - timedelta(days=n), d0 - timedelta(days=1)


def _avg_monthly(db: Session, conta_id, incl, d0: date, n: int):
    """Média mensal dos n meses completos anteriores a d0 (considera n meses mesmo sem movimentos)."""
    start, end = _month_start(d0, n), d0 - timedelta(days=1)
    desp, rec = _totals(db, conta_id, incl, start, end)
    return desp / n, rec / n


def _var(atual: Decimal, ref: Decimal) -> str | None:
    return None if ref == 0 else str(((atual - ref) / ref * 100).quantize(Decimal("0.01")))


@router.get("/summary")
def summary(
    data_de: date | None = None,
    data_ate: date | None = None,
    conta_id: int | None = None,
    incluir_transferencias: bool = False,
    _: Auth = Depends(require_auth),
    db: Session = Depends(get_db),
):
    d0, d1 = _period(db, data_de, data_ate)
    desp, rec = _totals(db, conta_id, incluir_transferencias, d0, d1)
    p0, p1 = _previous(d0, d1)
    pdesp, prec = _totals(db, conta_id, incluir_transferencias, p0, p1)
    medias = {}
    for n in (6, 12):
        md, mr = _avg_monthly(db, conta_id, incluir_transferencias, d0, n)
        medias[f"media_{n}m"] = {
            "despesas": _s(md),
            "receitas": _s(mr),
            "variacao_despesas_pct": _var(desp, md),
        }
    por_categorizar = db.scalar(
        select(func.count()).select_from(Movimento).where(Movimento.categoria_id.is_(None))
    )
    return {
        "periodo": {"data_de": d0, "data_ate": d1},
        "despesas": _s(desp),
        "receitas": _s(rec),
        "saldo_liquido": _s(rec - desp),
        "taxa_poupanca_pct": _pct(rec - desp, rec),
        "anterior": {
            "periodo": {"data_de": p0, "data_ate": p1},
            "despesas": _s(pdesp),
            "receitas": _s(prec),
            "variacao_despesas_pct": _var(desp, pdesp),
            "variacao_receitas_pct": _var(rec, prec),
        },
        **medias,
        "n_por_categorizar": por_categorizar,
    }


@router.get("/by-category")
def by_category(
    data_de: date | None = None,
    data_ate: date | None = None,
    conta_id: int | None = None,
    incluir_transferencias: bool = False,
    nivel: str = Query("filho", pattern="^(filho|pai)$"),
    _: Auth = Depends(require_auth),
    db: Session = Depends(get_db),
):
    d0, d1 = _period(db, data_de, data_ate)
    group_id = (
        func.coalesce(Categoria.parent_id, Categoria.id) if nivel == "pai" else Categoria.id
    )  # pai: sobe ao pai
    stmt = (
        _base(group_id, func.sum(-Movimento.montante), func.count())
        .where(Movimento.montante < 0, *_filters(conta_id, incluir_transferencias, d0, d1))
        .group_by(group_id)
    )
    rows = db.execute(stmt).all()
    names = {c.id: c for c in db.scalars(select(Categoria))}
    total = sum((Decimal(r[1]) for r in rows), ZERO)
    items = [
        {
            "categoria_id": gid,
            "nome": names[gid].nome if gid in names else "Por categorizar",
            "parent_id": names[gid].parent_id if gid in names else None,
            "cor": names[gid].cor if gid in names else None,
            "total": _s(Decimal(t)),
            "n": n,
            "percentagem": _pct(Decimal(t), total),
        }
        for gid, t, n in rows
    ]
    items.sort(key=lambda x: Decimal(x["total"]), reverse=True)
    return {"periodo": {"data_de": d0, "data_ate": d1}, "total_despesas": _s(total), "itens": items}


@router.get("/monthly")
def monthly(
    data_de: date | None = None,
    data_ate: date | None = None,
    conta_id: int | None = None,
    incluir_transferencias: bool = False,
    _: Auth = Depends(require_auth),
    db: Session = Depends(get_db),
):
    if not data_ate:
        data_ate = db.scalar(select(func.max(Movimento.data_movimento))) or date.today()
    if not data_de:
        data_de = _month_start(data_ate.replace(day=1), 11)
    mes = func.date_trunc("month", Movimento.data_movimento)
    rows = db.execute(
        _base(mes, DESPESA, RECEITA)
        .where(*_filters(conta_id, incluir_transferencias, data_de, data_ate))
        .group_by(mes)
        .order_by(mes)
    ).all()
    by_month = {r[0].date(): (Decimal(r[1]), Decimal(r[2])) for r in rows}
    out, cur = [], data_de.replace(day=1)
    while cur <= data_ate:  # inclui meses sem movimentos, a zero
        d, r = by_month.get(cur, (ZERO, ZERO))
        out.append(
            {"mes": cur.strftime("%Y-%m"), "despesas": _s(d), "receitas": _s(r), "saldo_liquido": _s(r - d)}
        )
        cur = _month_start(cur, -1)
    return {"meses": out}
