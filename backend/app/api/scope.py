"""Âmbito de contas (conta e/ou titular) partilhado pelos routers de movimentos e analytics (PRD 3.1/3.9)."""

from fastapi import HTTPException
from sqlalchemy import select

from ..models import Conta, Movimento


def scope_conds(conta_id: int | None, titular: str | None) -> list:
    """Condições sobre Movimento. `titular`: id de utilizador, ou "conjunta" (contas sem titular)."""
    conds = []
    if conta_id is not None:
        conds.append(Movimento.conta_id == conta_id)
    if titular:
        if titular == "conjunta":
            sub = select(Conta.id).where(Conta.titular_id.is_(None))
        elif titular.isdigit():
            sub = select(Conta.id).where(Conta.titular_id == int(titular))
        else:
            raise HTTPException(422, "titular deve ser um id de utilizador ou 'conjunta'")
        conds.append(Movimento.conta_id.in_(sub))
    return conds
