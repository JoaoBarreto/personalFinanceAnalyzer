import re
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ...deps import Auth, get_db, require_auth
from ...models import Categoria, Conta, Movimento, Regra
from ...services import categorizer
from ...services.categorizer import RuleData
from ...services.normalizer import normalize_pattern
from ..scope import get_owned

router = APIRouter(prefix="/api/rules", tags=["rules"])

TIPOS = "^(contem|comeca_por|igual|regex)$"
DIRECOES = "^(debito|credito|ambos)$"


class RuleIn(BaseModel):
    padrao: str = Field(min_length=1)
    tipo_match: str = Field(default="contem", pattern=TIPOS)
    categoria_id: int
    direcao: str = Field(default="ambos", pattern=DIRECOES)
    montante_min: Decimal | None = Field(default=None, ge=0)
    montante_max: Decimal | None = Field(default=None, ge=0)
    conta_id: int | None = None
    prioridade: int = 100
    ativa: bool = True

    @model_validator(mode="after")
    def _check(self):
        if (
            self.montante_min is not None
            and self.montante_max is not None
            and self.montante_min > self.montante_max
        ):
            raise ValueError("montante_min não pode ser maior que montante_max")
        if self.tipo_match == "regex":
            try:
                re.compile(self.padrao)
            except re.error as e:
                raise ValueError(f"regex inválida: {e}") from e
        elif len(normalize_pattern(self.padrao)) < 2:
            raise ValueError("padrão demasiado curto")
        return self


class RulePatch(BaseModel):
    padrao: str | None = Field(default=None, min_length=1)
    tipo_match: str | None = Field(default=None, pattern=TIPOS)
    categoria_id: int | None = None
    direcao: str | None = Field(default=None, pattern=DIRECOES)
    montante_min: Decimal | None = Field(default=None, ge=0)
    montante_max: Decimal | None = Field(default=None, ge=0)
    conta_id: int | None = None
    prioridade: int | None = None
    ativa: bool | None = None


def rule_out(r: Regra) -> dict:
    return {
        "id": r.id,
        "padrao": r.padrao,
        "tipo_match": r.tipo_match,
        "categoria_id": r.categoria_id,
        "direcao": r.direcao,
        "montante_min": None if r.montante_min is None else str(r.montante_min),
        "montante_max": None if r.montante_max is None else str(r.montante_max),
        "conta_id": r.conta_id,
        "prioridade": r.prioridade,
        "origem": r.origem,
        "ativa": r.ativa,
        "n_aplicacoes": r.n_aplicacoes,
    }


def _store_pattern(padrao: str, tipo: str) -> str:
    return padrao if tipo == "regex" else normalize_pattern(padrao)


def _check_refs(db: Session, user, categoria_id: int | None, conta_id: int | None):
    if categoria_id is not None:
        get_owned(db, Categoria, categoria_id, user, status=422, msg="Categoria inexistente")
    if conta_id is not None:
        get_owned(db, Conta, conta_id, user, status=422, msg="Conta inexistente")


def draft(body: RuleIn, rule_id: int | None = None) -> RuleData:
    return RuleData(
        rule_id,
        _store_pattern(body.padrao, body.tipo_match),
        body.tipo_match,
        body.categoria_id,
        body.direcao,
        body.montante_min,
        body.montante_max,
        body.conta_id,
        body.prioridade,
    )


def _like(text: str) -> str:
    return "%" + text.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_") + "%"


@router.get("/search")
def search_rules(
    q: str | None = None,
    categoria_id: int | None = None,
    ativa: bool | None = None,
    origem: str | None = Query(None, pattern="^(manual|aprendida)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    auth: Auth = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Regras paginadas, com pesquisa (palavra-chave ou nome da categoria) e filtros."""
    stmt = (
        select(Regra, Categoria.nome)
        .join(Categoria, Categoria.id == Regra.categoria_id)
        .where(Regra.dono_id == auth.utilizador.id)
    )
    if q and q.strip():
        stmt = stmt.where(
            or_(
                Regra.padrao.ilike(_like(normalize_pattern(q)), escape="\\"),
                Categoria.nome.ilike(_like(q.strip()), escape="\\"),
            )
        )
    if categoria_id is not None:
        stmt = stmt.where(Regra.categoria_id == categoria_id)
    if ativa is not None:
        stmt = stmt.where(Regra.ativa.is_(ativa))
    if origem:
        stmt = stmt.where(Regra.origem == origem)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(
        stmt.order_by(Regra.prioridade.desc(), Regra.padrao, Regra.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [{**rule_out(r), "categoria_nome": nome} for r, nome in rows],
    }


@router.get("")
def list_rules(auth: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    q = select(Regra).where(Regra.dono_id == auth.utilizador.id).order_by(Regra.prioridade.desc(), Regra.id)
    return [rule_out(r) for r in db.scalars(q)]


@router.post("", status_code=201)
def create_rule(body: RuleIn, auth: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    _check_refs(db, auth.utilizador, body.categoria_id, body.conta_id)
    r = Regra(
        **{**body.model_dump(), "padrao": _store_pattern(body.padrao, body.tipo_match)},
        origem="manual",
        dono_id=auth.utilizador.id,
        criado_por=auth.utilizador.id,
        atualizado_por=auth.utilizador.id,
    )
    db.add(r)
    db.commit()
    return rule_out(r)


@router.patch("/{rule_id}")
def patch_rule(
    rule_id: int, body: RulePatch, auth: Auth = Depends(require_auth), db: Session = Depends(get_db)
):
    r = get_owned(db, Regra, rule_id, auth.utilizador)
    data = body.model_dump(exclude_unset=True)
    merged = {**rule_out(r), **data}
    try:  # reutiliza as validações do corpo completo
        full = RuleIn(**{k: merged[k] for k in RuleIn.model_fields})
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    _check_refs(db, auth.utilizador, data.get("categoria_id"), data.get("conta_id"))
    for k in RuleIn.model_fields:
        setattr(r, k, getattr(full, k))
    r.padrao = _store_pattern(full.padrao, full.tipo_match)
    r.atualizado_por, r.atualizada_em = auth.utilizador.id, datetime.now(UTC)
    db.commit()
    return rule_out(r)


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: int, auth: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    r = get_owned(db, Regra, rule_id, auth.utilizador)
    db.delete(r)  # movimentos.regra_id passa a NULL (ON DELETE SET NULL); a categoria mantém-se
    db.commit()


@router.post("/preview-impact")
def preview_draft(
    body: RuleIn,
    linhas: int = Query(0, ge=0, le=500),
    auth: Auth = Depends(require_auth),
    db: Session = Depends(get_db),
):
    _check_refs(db, auth.utilizador, body.categoria_id, body.conta_id)
    return categorizer.impact(db, draft(body), auth.utilizador.id, linhas)


@router.post("/{rule_id}/preview-impact")
def preview_impact(rule_id: int, auth: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    r = get_owned(db, Regra, rule_id, auth.utilizador)
    return categorizer.impact(db, RuleData.of(r), auth.utilizador.id)


@router.post("/apply")
def apply_rules(auth: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    """Aplicação retroativa: reavalia regras e histórico em todos os movimentos não-manuais do utilizador."""
    uid = auth.utilizador.id
    movs = db.scalars(
        select(Movimento).where(
            Movimento.categoria_origem.is_distinct_from("manual"), categorizer.owned_movements(uid)
        )
    ).all()
    res = categorizer.categorize(db, list(movs), uid, only_uncategorized=False)
    db.commit()
    return {
        "movimentos_alterados": sum(res.applied.values()),
        "libertados": res.released,  # a regra deixou de os apanhar: voltam a «por categorizar»
        "por_regra": res.applied,
    }
