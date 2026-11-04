"""Âmbito por dono: cada utilizador só vê e altera o que é seu (contas, regras, categorias e, por herança da conta,
movimentos, importações e categorizações guardadas).

Todos os routers usam estes ajudantes; `tests/test_isolation.py` exige 404/vazio para dados de outro utilizador.
"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Categoria, Conta, Importacao, Movimento, Regra, Utilizador

_MSG = {
    Conta: "Conta não encontrada",
    Regra: "Regra não encontrada",
    Categoria: "Categoria não encontrada",
    Movimento: "Movimento não encontrado",
    Importacao: "Importação não encontrada",
}


def owned_account_ids(user: Utilizador):
    """Subconsulta com os ids das contas do utilizador."""
    return select(Conta.id).where(Conta.dono_id == user.id)


def scope_conds(user: Utilizador, conta_id: int | None = None) -> list:
    """Condições sobre Movimento: só contas do utilizador (e, opcionalmente, uma conta em particular)."""
    conds = [Movimento.conta_id.in_(owned_account_ids(user))]
    if conta_id is not None:
        conds.append(Movimento.conta_id == conta_id)
    return conds


def get_owned(
    db: Session, model, obj_id: int, user: Utilizador, *, status: int = 404, msg: str | None = None
):
    """Obtém um objeto do utilizador; de outro utilizador ou inexistente dá o MESMO erro (não revela que existe)."""
    obj = db.get(model, obj_id)
    ok = False
    if obj is not None:
        if model in (Conta, Regra, Categoria):
            ok = obj.dono_id == user.id
        else:  # Movimento / Importacao: o dono vem da conta
            ok = db.scalar(select(Conta.dono_id).where(Conta.id == obj.conta_id)) == user.id
    if not ok:
        raise HTTPException(status, msg or _MSG[model])
    return obj
