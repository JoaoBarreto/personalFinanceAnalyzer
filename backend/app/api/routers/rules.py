import re
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...deps import Auth, get_db, require_auth
from ...models import Categoria, Conta, Movimento, Regra
from ...services import categorizer
from ...services.categorizer import RuleData
from ...services.normalizer import normalize_pattern

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


def _check_refs(db: Session, categoria_id: int | None, conta_id: int | None):
    if categoria_id is not None and db.get(Categoria, categoria_id) is None:
        raise HTTPException(422, "Categoria inexistente")
    if conta_id is not None and db.get(Conta, conta_id) is None:
        raise HTTPException(422, "Conta inexistente")


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


@router.get("")
def list_rules(_: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    return [rule_out(r) for r in db.scalars(select(Regra).order_by(Regra.prioridade.desc(), Regra.id))]


@router.post("", status_code=201)
def create_rule(body: RuleIn, auth: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    _check_refs(db, body.categoria_id, body.conta_id)
    r = Regra(
        **{**body.model_dump(), "padrao": _store_pattern(body.padrao, body.tipo_match)},
        origem="manual",
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
    r = db.get(Regra, rule_id)
    if r is None:
        raise HTTPException(404, "Regra não encontrada")
    data = body.model_dump(exclude_unset=True)
    merged = {**rule_out(r), **data}
    try:  # reutiliza as validações do corpo completo
        full = RuleIn(**{k: merged[k] for k in RuleIn.model_fields})
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    _check_refs(db, data.get("categoria_id"), data.get("conta_id"))
    for k in RuleIn.model_fields:
        setattr(r, k, getattr(full, k))
    r.padrao = _store_pattern(full.padrao, full.tipo_match)
    r.atualizado_por, r.atualizada_em = auth.utilizador.id, datetime.now(UTC)
    db.commit()
    return rule_out(r)


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: int, _: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    r = db.get(Regra, rule_id)
    if r is None:
        raise HTTPException(404, "Regra não encontrada")
    db.delete(r)  # movimentos.regra_id passa a NULL (ON DELETE SET NULL); a categoria mantém-se
    db.commit()


@router.post("/preview-impact")
def preview_draft(body: RuleIn, _: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    _check_refs(db, body.categoria_id, body.conta_id)
    return categorizer.impact(db, draft(body))


@router.post("/{rule_id}/preview-impact")
def preview_impact(rule_id: int, _: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    r = db.get(Regra, rule_id)
    if r is None:
        raise HTTPException(404, "Regra não encontrada")
    return categorizer.impact(db, RuleData.of(r))


@router.post("/apply")
def apply_rules(_: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    """Aplicação retroativa: reavalia regras e histórico em todos os movimentos não-manuais."""
    movs = db.scalars(select(Movimento).where(Movimento.categoria_origem.is_distinct_from("manual"))).all()
    applied = categorizer.categorize(db, list(movs), only_uncategorized=False)
    db.commit()
    return {"movimentos_alterados": sum(applied.values()), "por_regra": applied}
