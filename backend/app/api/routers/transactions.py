from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ...deps import Auth, get_db, require_auth
from ...models import Categoria, Movimento, Regra
from ...services import categorizer
from ...services.normalizer import normalize_pattern, suggest_keyword
from ..scope import scope_conds
from .rules import RuleIn, draft, rule_out

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def _out(m: Movimento, cat: Categoria | None) -> dict:
    return {
        "id": m.id,
        "conta_id": m.conta_id,
        "data_movimento": m.data_movimento,
        "data_valor": m.data_valor,
        "descricao_original": m.descricao_original,
        "descricao_normalizada": m.descricao_normalizada,
        "montante": str(m.montante),
        "saldo_apos": None if m.saldo_apos is None else str(m.saldo_apos),
        "categoria_id": m.categoria_id,
        "categoria_nome": cat.nome if cat else None,
        "categoria_origem": m.categoria_origem,
        "regra_id": m.regra_id,
        "notas": m.notas,
        "atualizado_por": m.atualizado_por,
        "importacao_id": m.importacao_id,
    }


def _like(text: str) -> str:
    return "%" + text.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_") + "%"


@router.get("")
def list_transactions(
    _: Auth = Depends(require_auth),
    db: Session = Depends(get_db),
    conta_id: int | None = None,
    titular: str | None = None,
    categoria_id: int | None = None,
    sem_categoria: bool = False,
    data_de: date | None = None,
    data_ate: date | None = None,
    montante_min: Decimal | None = None,
    montante_max: Decimal | None = None,
    q: str | None = None,
    incluir_transferencias: bool = True,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    stmt = select(Movimento, Categoria).outerjoin(Categoria, Categoria.id == Movimento.categoria_id)
    stmt = stmt.where(*scope_conds(conta_id, titular))
    if sem_categoria:
        stmt = stmt.where(Movimento.categoria_id.is_(None))
    elif categoria_id is not None:
        stmt = stmt.where(Movimento.categoria_id == categoria_id)
    if data_de:
        stmt = stmt.where(Movimento.data_movimento >= data_de)
    if data_ate:
        stmt = stmt.where(Movimento.data_movimento <= data_ate)
    if montante_min is not None:
        stmt = stmt.where(Movimento.montante >= montante_min)
    if montante_max is not None:
        stmt = stmt.where(Movimento.montante <= montante_max)
    if not incluir_transferencias:
        stmt = stmt.where(or_(Categoria.tipo.is_(None), Categoria.tipo != "transferencia"))
    if q:
        stmt = stmt.where(
            or_(
                Movimento.descricao_normalizada.ilike(_like(normalize_pattern(q)), escape="\\"),
                Movimento.descricao_original.ilike(_like(q), escape="\\"),
                Movimento.notas.ilike(_like(q), escape="\\"),
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(
        stmt.order_by(Movimento.data_movimento.desc(), Movimento.ordem_no_dia.desc(), Movimento.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {"total": total, "page": page, "page_size": page_size, "items": [_out(m, c) for m, c in rows]}


@router.get("/uncategorized")
def uncategorized(
    group_by: str | None = Query(None, pattern="^description$"),
    _: Auth = Depends(require_auth),
    db: Session = Depends(get_db),
):
    base = Movimento.categoria_id.is_(None)
    total = db.scalar(select(func.count()).select_from(Movimento).where(base))
    if group_by is None:
        rows = db.execute(
            select(Movimento, Categoria)
            .outerjoin(Categoria, Categoria.id == Movimento.categoria_id)
            .where(base)
            .order_by(Movimento.data_movimento.desc(), Movimento.id.desc())
            .limit(500)
        ).all()
        return {"total": total, "items": [_out(m, c) for m, c in rows]}
    rows = db.execute(
        select(
            Movimento.descricao_normalizada,
            func.count(),
            func.sum(Movimento.montante),
            func.min(Movimento.descricao_original),
            func.array_agg(Movimento.id),
        )
        .where(base)
        .group_by(Movimento.descricao_normalizada)
        .order_by(func.count().desc(), Movimento.descricao_normalizada)
    ).all()
    grupos = [
        {
            "descricao_normalizada": d,
            "n": n,
            "total": str(s),
            "exemplo_original": ex,
            "keyword_sugerida": suggest_keyword(d),
            "ids": sorted(ids),
        }
        for d, n, s, ex, ids in rows
    ]
    return {"total": total, "grupos": grupos}


class TransactionPatch(BaseModel):
    categoria_id: int | None = None  # null explícito = remover categoria
    notas: str | None = None


@router.patch("/{tx_id}")
def patch_transaction(
    tx_id: int, body: TransactionPatch, auth: Auth = Depends(require_auth), db: Session = Depends(get_db)
):
    m = db.get(Movimento, tx_id)
    if m is None:
        raise HTTPException(404, "Movimento não encontrado")
    fields = body.model_fields_set
    if "categoria_id" in fields:
        _set_category(db, [m], body.categoria_id, auth.utilizador.id)
    if "notas" in fields:
        m.notas = body.notas
    m.atualizado_por = auth.utilizador.id
    db.commit()
    return _out(m, db.get(Categoria, m.categoria_id) if m.categoria_id else None)


def _set_category(db: Session, movs: list[Movimento], categoria_id: int | None, user_id: int) -> None:
    if categoria_id is not None:
        cat = db.get(Categoria, categoria_id)
        if cat is None or not cat.ativa:
            raise HTTPException(422, "Categoria inexistente ou inativa")
    for m in movs:
        # categorização manual: nunca é sobrescrita por regras (categoria_origem = 'manual')
        m.categoria_id = categoria_id
        m.categoria_origem = "manual" if categoria_id is not None else None
        m.regra_id = None
        m.atualizado_por = user_id


class LearnRule(BaseModel):
    padrao: str = Field(min_length=1)
    tipo_match: str = Field(default="contem", pattern="^(contem|comeca_por)$")
    # Por omissão a regra aplica-se a TODOS os movimentos já importados (os manuais nunca são tocados)
    aplicar_retroativamente: bool = True


class BulkCategorize(BaseModel):
    ids: list[int] | None = None
    descricao_normalizada: str | None = None  # alternativa: todos os movimentos com esta descrição
    categoria_id: int
    criar_regra: LearnRule | None = None
    excluir_ids: list[
        int
    ] = []  # linhas que o utilizador desmarcou: ficam como estão (nem o grupo nem a regra lhes tocam)

    @model_validator(mode="after")
    def _one_selector(self):
        if (self.ids is None) == (self.descricao_normalizada is None):
            raise ValueError("indique ids ou descricao_normalizada (apenas um)")
        return self


def _estado(m: Movimento) -> tuple:
    return (m.categoria_id, m.categoria_origem, m.regra_id)


@router.post("/bulk-categorize")
def bulk_categorize(body: BulkCategorize, auth: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    stmt = select(Movimento)
    stmt = (
        stmt.where(Movimento.id.in_(body.ids))
        if body.ids is not None
        else stmt.where(Movimento.descricao_normalizada == body.descricao_normalizada)
    )
    excl = set(body.excluir_ids)
    movs = [m for m in db.scalars(stmt) if m.id not in excl]
    if not movs:
        raise HTTPException(404, "Nenhum movimento encontrado")
    retro = bool(body.criar_regra and body.criar_regra.aplicar_retroativamente)
    candidatos = (
        [
            m
            for m in db.scalars(
                select(Movimento).where(Movimento.categoria_origem.is_distinct_from("manual"))
            )
            if m.id not in excl
        ]
        if retro
        else []
    )
    antes = {m.id: _estado(m) for m in [*movs, *candidatos]}  # para a lista de alterações e para o «Desfazer»
    _set_category(db, movs, body.categoria_id, auth.utilizador.id)
    out: dict = {"categorizados": len(movs), "regra": None, "impacto": None, "aplicados": 0}
    if body.criar_regra:
        lr = body.criar_regra
        try:
            rin = RuleIn(padrao=lr.padrao, tipo_match=lr.tipo_match, categoria_id=body.categoria_id)
        except ValidationError as e:
            raise HTTPException(422, "; ".join(x["msg"] for x in e.errors())) from e
        db.flush()
        out["impacto"] = categorizer.impact(db, draft(rin))  # inclui alerta de conflitos (outra categoria)
        r = Regra(
            padrao=normalize_pattern(lr.padrao),
            tipo_match=lr.tipo_match,
            categoria_id=body.categoria_id,
            origem="aprendida",
            criado_por=auth.utilizador.id,
            atualizado_por=auth.utilizador.id,
        )
        db.add(r)
        db.flush()
        out["regra"] = rule_out(r)
        if retro:
            applied = categorizer.categorize(db, candidatos, only_uncategorized=False)
            out["aplicados"] = sum(applied.values())  # outras linhas categorizadas pela nova regra
    # tudo o que mudou, com o estado anterior (permite corrigir linha a linha e «Desfazer»)
    por_id = {m.id: m for m in [*movs, *candidatos]}
    nomes = {c.id: c.nome for c in db.scalars(select(Categoria))}
    out["alteradas"] = [
        {
            "id": m.id,
            "data_movimento": m.data_movimento,
            "descricao_original": m.descricao_original,
            "montante": str(m.montante),
            "categoria_id": m.categoria_id,
            "categoria_nome": nomes.get(m.categoria_id),
            "do_grupo": m in movs,
            "anterior": dict(zip(("categoria_id", "categoria_origem", "regra_id"), antes[m.id], strict=True)),
        }
        for m in sorted(por_id.values(), key=lambda m: (m.data_movimento, m.id))
        if _estado(m) != antes[m.id]
    ]
    db.commit()
    return out


class RestoreItem(BaseModel):
    id: int
    categoria_id: int | None
    categoria_origem: str | None = Field(default=None, pattern="^(regra|historico|fuzzy|ml|manual)$")
    regra_id: int | None = None

    @model_validator(mode="after")
    def _par(self):
        if (self.categoria_id is None) != (self.categoria_origem is None):
            raise ValueError("categoria_id e categoria_origem têm de vir os dois ou nenhum")
        return self


class Restore(BaseModel):
    itens: list[RestoreItem]
    apagar_regra_id: int | None = None


@router.post("/restore")
def restore(body: Restore, auth: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    """Desfaz uma categorização em lote: repõe o estado anterior e apaga a regra criada nessa ação."""
    n = 0
    for it in body.itens:
        m = db.get(Movimento, it.id)
        if m is None:
            continue
        if it.categoria_id is not None and db.get(Categoria, it.categoria_id) is None:
            raise HTTPException(422, "Categoria anterior inexistente")
        m.categoria_id, m.categoria_origem = it.categoria_id, it.categoria_origem
        m.regra_id = it.regra_id if it.regra_id and db.get(Regra, it.regra_id) else None
        m.atualizado_por = auth.utilizador.id
        n += 1
    apagada = False
    if body.apagar_regra_id is not None and (r := db.get(Regra, body.apagar_regra_id)) is not None:
        db.delete(r)
        apagada = True
    db.commit()
    return {"restaurados": n, "regra_apagada": apagada}
