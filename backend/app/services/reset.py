"""Reposição dos dados importados, mantendo o trabalho de categorização.

Apaga os movimentos e importações (qualquer estado) das contas de UM utilizador. Mantém utilizadores, contas, categorias e regras.
Cada categorização feita à mão fica guardada com a data e a descrição da linha (`categorizacoes_guardadas`) e
reaplica-se exatamente quando o extrato é reimportado, incluindo as exceções (a mesma descrição com categorias
diferentes). As categorizações por regra voltam sozinhas, porque as regras ficam.
"""

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from ..models import CategorizacaoGuardada, Conta, Importacao, Movimento, Regra
from .saved_categorization import save_manual


def _contas(dono_id: int):
    return select(Conta.id).where(Conta.dono_id == dono_id)


def preview(db: Session, dono_id: int) -> dict[str, int]:
    manuais = list(
        db.scalars(
            select(Movimento).where(
                Movimento.categoria_origem == "manual", Movimento.conta_id.in_(_contas(dono_id))
            )
        )
    )
    por_desc: dict[str, set[int]] = {}
    for m in manuais:
        por_desc.setdefault(m.descricao_normalizada, set()).add(m.categoria_id)
    return {
        "movimentos": db.scalar(
            select(func.count()).select_from(Movimento).where(Movimento.conta_id.in_(_contas(dono_id)))
        ),
        "importacoes": db.scalar(
            select(func.count()).select_from(Importacao).where(Importacao.conta_id.in_(_contas(dono_id)))
        ),
        "categorizacoes_manuais": len(manuais),
        "descricoes_com_excecoes": sum(1 for c in por_desc.values() if len(c) > 1),
    }


def reset_movements(db: Session, dono_id: int) -> dict[str, int]:
    contas = _contas(dono_id)
    guardadas = save_manual(
        db,
        db.scalars(
            select(Movimento).where(Movimento.categoria_origem == "manual", Movimento.conta_id.in_(contas))
        ),
    )
    movs = db.execute(delete(Movimento).where(Movimento.conta_id.in_(contas))).rowcount
    imps = db.execute(delete(Importacao).where(Importacao.conta_id.in_(contas))).rowcount
    db.execute(update(Regra).where(Regra.dono_id == dono_id).values(n_aplicacoes=0))
    db.commit()
    return {
        "movimentos_apagados": movs,
        "importacoes_apagadas": imps,
        "categorizacoes_guardadas": guardadas,
        "total_guardadas_agora": db.scalar(
            select(func.count())
            .select_from(CategorizacaoGuardada)
            .where(CategorizacaoGuardada.conta_id.in_(contas))
        ),
    }
