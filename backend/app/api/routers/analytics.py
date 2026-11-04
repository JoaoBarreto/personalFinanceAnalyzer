"""Agregações do dashboard (PRD 3.9), em SQL.

Convenções: despesa = montante < 0, receita = montante > 0 (reembolsos só na Fase 2). Movimentos cuja categoria
é do tipo `transferencia` contam como movimentos normais (`incluir_transferencias=false` é só um filtro opcional da API). Dinheiro sempre em string.
"""

import calendar
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from ...deps import Auth, get_db, require_auth
from ...models import Categoria, Movimento
from ...services.balances import saldo_abertura, saldo_em
from ..scope import scope_conds

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

ZERO = Decimal(0)
DESPESA = func.coalesce(func.sum(case((Movimento.montante < 0, -Movimento.montante), else_=0)), 0)
RECEITA = func.coalesce(func.sum(case((Movimento.montante > 0, Movimento.montante), else_=0)), 0)


def _filters(scope, incluir_transferencias, d0=None, d1=None):
    conds = list(scope)
    if d0:
        conds.append(Movimento.data_movimento >= d0)
    if d1:
        conds.append(Movimento.data_movimento <= d1)
    if not incluir_transferencias:
        conds.append(or_(Categoria.tipo.is_(None), Categoria.tipo != "transferencia"))
    return conds


def _base(*cols):
    return select(*cols).select_from(Movimento).outerjoin(Categoria, Categoria.id == Movimento.categoria_id)


def _totals(db: Session, scope, incl, d0, d1) -> tuple[Decimal, Decimal]:
    r = db.execute(_base(DESPESA, RECEITA).where(*_filters(scope, incl, d0, d1))).one()
    return Decimal(r[0]), Decimal(r[1])


def _transfer_net(db: Session, scope, d0: date, d1: date) -> Decimal:
    """Soma (com sinal) dos movimentos de categorias do tipo transferência no período."""
    q = (
        select(func.coalesce(func.sum(Movimento.montante), 0))
        .select_from(Movimento)
        .join(Categoria, Categoria.id == Movimento.categoria_id)
        .where(Categoria.tipo == "transferencia", Movimento.data_movimento.between(d0, d1), *scope)
    )
    return Decimal(db.scalar(q))


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
    if d0 == date(d0.year, 1, 1) and d1 == date(d0.year, 12, 31):  # ano civil completo -> ano anterior
        return date(d0.year - 1, 1, 1), date(d0.year - 1, 12, 31)
    full_month = d0.day == 1 and d1 == d0.replace(day=calendar.monthrange(d0.year, d0.month)[1])
    if full_month:
        p0 = _month_start(d0, 1)
        return p0, d0 - timedelta(days=1)
    n = (d1 - d0).days + 1
    return d0 - timedelta(days=n), d0 - timedelta(days=1)


def _avg_monthly(db: Session, scope, incl, d0: date, n: int):
    """Média mensal dos até n meses completos anteriores ao mês de d0, só desde o 1.º movimento.

    Devolve None quando não há nenhum mês completo com histórico (em vez de dividir por meses inexistentes).
    """
    first = db.scalar(select(func.min(Movimento.data_movimento)).where(*scope))
    if first is None:
        return None
    cur = d0.replace(day=1)
    start = max(_month_start(cur, n), first.replace(day=1))
    months = (cur.year * 12 + cur.month) - (start.year * 12 + start.month)
    if months <= 0:
        return None
    desp, rec = _totals(db, scope, incl, start, cur - timedelta(days=1))
    return desp / months, rec / months


def _var(atual: Decimal, ref: Decimal) -> str | None:
    return None if ref == 0 else str(((atual - ref) / ref * 100).quantize(Decimal("0.01")))


@router.get("/summary")
def summary(
    data_de: date | None = None,
    data_ate: date | None = None,
    conta_id: int | None = None,
    titular: str | None = None,
    incluir_transferencias: bool = True,
    _: Auth = Depends(require_auth),
    db: Session = Depends(get_db),
):
    scope = scope_conds(conta_id, titular)
    d0, d1 = _period(db, data_de, data_ate)
    desp, rec = _totals(db, scope, incluir_transferencias, d0, d1)
    desp_x, rec_x = _totals(db, scope, False, d0, d1)
    p0, p1 = _previous(d0, d1)
    pdesp, prec = _totals(db, scope, incluir_transferencias, p0, p1)
    medias = {}
    for n in (6, 12):
        avg = _avg_monthly(db, scope, incluir_transferencias, d0, n)
        medias[f"media_{n}m"] = (
            {"despesas": None, "receitas": None, "variacao_despesas_pct": None}
            if avg is None
            else {"despesas": _s(avg[0]), "receitas": _s(avg[1]), "variacao_despesas_pct": _var(desp, avg[0])}
        )
    inicio, fim = saldo_abertura(db, scope, d0, d1), saldo_em(db, scope, d1)
    transf = ZERO if incluir_transferencias else _transfer_net(db, scope, d0, d1)  # senão já estão nos totais
    diferenca = None if inicio is None or fim is None else fim - (inicio + rec - desp + transf)
    por_categorizar = db.scalar(
        select(func.count()).select_from(Movimento).where(Movimento.categoria_id.is_(None))
    )
    return {
        "periodo": {"data_de": d0, "data_ate": d1},
        "despesas": _s(desp),
        "receitas": _s(rec),
        "poupanca": _s(rec - desp),
        "saldo": {
            "inicio": None if inicio is None else _s(inicio),
            "fim": None if fim is None else _s(fim),
            "transferencias": _s(transf),
            "diferenca": None if diferenca is None else _s(diferenca),
            "reconcilia": None if diferenca is None else diferenca == 0,
        },
        # Dinheiro enviado para fora da conta (poupança/investimento, depósitos...) = transferências líquidas de saída.
        "investido": _s(-_transfer_net(db, scope, d0, d1)),
        # A taxa conta o dinheiro investido como poupado: usa receitas/despesas sem transferências.
        "taxa_poupanca_pct": _pct(rec_x - desp_x, rec_x),
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
    titular: str | None = None,
    incluir_transferencias: bool = True,
    nivel: str = Query("filho", pattern="^(filho|pai)$"),
    _: Auth = Depends(require_auth),
    db: Session = Depends(get_db),
):
    scope = scope_conds(conta_id, titular)
    d0, d1 = _period(db, data_de, data_ate)
    group_id = (
        func.coalesce(Categoria.parent_id, Categoria.id) if nivel == "pai" else Categoria.id
    )  # pai: sobe ao pai
    stmt = (
        _base(group_id, func.sum(-Movimento.montante), func.count())
        .where(Movimento.montante < 0, *_filters(scope, incluir_transferencias, d0, d1))
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


def _next_period(d: date, gran: str) -> date:
    return date(d.year + 1, 1, 1) if gran == "ano" else _month_start(d, -1)


@router.get("/monthly")
def monthly(
    data_de: date | None = None,
    data_ate: date | None = None,
    conta_id: int | None = None,
    titular: str | None = None,
    incluir_transferencias: bool = True,
    granularidade: str = Query("mes", pattern="^(mes|ano)$"),
    _: Auth = Depends(require_auth),
    db: Session = Depends(get_db),
):
    scope = scope_conds(conta_id, titular)
    if not data_ate:
        data_ate = db.scalar(select(func.max(Movimento.data_movimento))) or date.today()
    if not data_de:
        if granularidade == "ano":  # desde o ano do 1.º movimento
            first = db.scalar(select(func.min(Movimento.data_movimento))) or data_ate
            data_de = date(first.year, 1, 1)
        else:
            data_de = _month_start(data_ate.replace(day=1), 11)
    trunc = func.date_trunc("year" if granularidade == "ano" else "month", Movimento.data_movimento)
    rows = db.execute(
        _base(trunc, DESPESA, RECEITA)
        .where(*_filters(scope, incluir_transferencias, data_de, data_ate))
        .group_by(trunc)
        .order_by(trunc)
    ).all()
    by_period = {r[0].date(): (Decimal(r[1]), Decimal(r[2])) for r in rows}
    out, cur = [], date(data_de.year, 1, 1) if granularidade == "ano" else data_de.replace(day=1)
    while cur <= data_ate:  # inclui períodos sem movimentos, a zero
        nxt = _next_period(cur, granularidade)
        d, r = by_period.get(cur, (ZERO, ZERO))
        fim = saldo_em(db, scope, nxt - timedelta(days=1))
        out.append(
            {
                "periodo": cur.strftime("%Y" if granularidade == "ano" else "%Y-%m"),
                "despesas": _s(d),
                "receitas": _s(r),
                "poupanca": _s(r - d),
                "saldo_fim": None if fim is None else _s(fim),
            }
        )
        cur = nxt
    return {"granularidade": granularidade, "periodos": out}


@router.get("/category-matrix")
def category_matrix(
    data_de: date | None = None,
    data_ate: date | None = None,
    conta_id: int | None = None,
    titular: str | None = None,
    incluir_transferencias: bool = True,
    nivel: str = Query("pai", pattern="^(filho|pai)$"),
    _: Auth = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Despesas por categoria × mês (só montante < 0, como em by-category). Por omissão, o ano do último movimento."""
    scope = scope_conds(conta_id, titular)
    if not data_de or not data_ate:
        last = db.scalar(select(func.max(Movimento.data_movimento))) or date.today()
        data_de, data_ate = data_de or date(last.year, 1, 1), data_ate or date(last.year, 12, 31)
    group_id = func.coalesce(Categoria.parent_id, Categoria.id) if nivel == "pai" else Categoria.id
    mes = func.date_trunc("month", Movimento.data_movimento)
    rows = db.execute(
        _base(group_id, mes, func.sum(-Movimento.montante))
        .where(Movimento.montante < 0, *_filters(scope, incluir_transferencias, data_de, data_ate))
        .group_by(group_id, mes)
    ).all()
    meses, cur = [], data_de.replace(day=1)
    while cur <= data_ate:
        meses.append(cur.strftime("%Y-%m"))
        cur = _month_start(cur, -1)
    names = {c.id: c.nome for c in db.scalars(select(Categoria))}
    cells: dict[int | None, dict[str, Decimal]] = {}
    for gid, m, v in rows:
        cells.setdefault(gid, {})[m.strftime("%Y-%m")] = Decimal(v)
    linhas = []
    for gid, vals in cells.items():
        total = sum(vals.values(), ZERO)
        linhas.append(
            {
                "categoria_id": gid,
                "nome": names.get(gid, "Por categorizar"),
                "valores": {m: _s(vals.get(m, ZERO)) for m in meses},
                "total": _s(total),
            }
        )
    linhas.sort(key=lambda x: Decimal(x["total"]), reverse=True)
    totais = {m: _s(sum((c.get(m, ZERO) for c in cells.values()), ZERO)) for m in meses}
    return {
        "periodo": {"data_de": data_de, "data_ate": data_ate},
        "meses": meses,
        "linhas": linhas,
        "totais": totais,
        "total": _s(sum((Decimal(v) for v in totais.values()), ZERO)),
    }
