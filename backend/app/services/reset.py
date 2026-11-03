"""Reposição dos dados importados, mantendo o trabalho de categorização.

Apaga TODOS os movimentos e importações (qualquer estado). Mantém utilizadores, contas, categorias e regras.
Cada categorização feita à mão fica guardada com a data e a descrição da linha (`categorizacoes_guardadas`) e
reaplica-se exatamente quando o extrato é reimportado, incluindo as exceções (a mesma descrição com categorias
diferentes). As categorizações por regra voltam sozinhas, porque as regras ficam.
"""

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from ..models import CategorizacaoGuardada, Importacao, Movimento, Regra
from .saved_categorization import save_manual


def preview(db: Session) -> dict[str, int]:
    manuais = list(db.scalars(select(Movimento).where(Movimento.categoria_origem == "manual")))
    por_desc: dict[str, set[int]] = {}
    for m in manuais:
        por_desc.setdefault(m.descricao_normalizada, set()).add(m.categoria_id)
    return {
        "movimentos": db.scalar(select(func.count()).select_from(Movimento)),
        "importacoes": db.scalar(select(func.count()).select_from(Importacao)),
        "categorizacoes_manuais": len(manuais),
        "descricoes_com_excecoes": sum(1 for c in por_desc.values() if len(c) > 1),
    }


def reset_movements(db: Session) -> dict[str, int]:
    guardadas = save_manual(db, db.scalars(select(Movimento).where(Movimento.categoria_origem == "manual")))
    movs = db.execute(delete(Movimento)).rowcount
    imps = db.execute(delete(Importacao)).rowcount
    db.execute(update(Regra).values(n_aplicacoes=0))
    db.commit()
    return {
        "movimentos_apagados": movs,
        "importacoes_apagadas": imps,
        "categorizacoes_guardadas": guardadas,
        "total_guardadas_agora": db.scalar(select(func.count()).select_from(CategorizacaoGuardada)),
    }
