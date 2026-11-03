"""Categorizações manuais que sobrevivem ao apagar movimentos (reset, reversão de importação).

Guardam-se por (conta, data, descrição normalizada) e reaplicam-se, uma a uma, quando a mesma linha volta a ser
importada. As escolhas feitas à mão (incluindo exceções para a mesma descrição) voltam exatamente como estavam.
"""

from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CategorizacaoGuardada, Movimento


def save_manual(db: Session, movs: Iterable[Movimento]) -> int:
    n = 0
    for m in movs:
        if m.categoria_origem == "manual" and m.categoria_id is not None:
            db.add(
                CategorizacaoGuardada(
                    conta_id=m.conta_id,
                    data_movimento=m.data_movimento,
                    descricao_normalizada=m.descricao_normalizada,
                    categoria_id=m.categoria_id,
                )
            )
            n += 1
    return n


def apply_saved(db: Session, conta_id: int, novos: list[Movimento], user_id: int | None) -> int:
    """Marca como manuais os movimentos novos que coincidem com uma categorização guardada; consome-a."""
    if not novos:
        return 0
    datas = {m.data_movimento for m in novos}
    pool: dict[tuple, list[CategorizacaoGuardada]] = defaultdict(list)
    q = (
        select(CategorizacaoGuardada)
        .where(CategorizacaoGuardada.conta_id == conta_id, CategorizacaoGuardada.data_movimento.in_(datas))
        .order_by(CategorizacaoGuardada.id)
    )
    for g in db.scalars(q):
        pool[(g.data_movimento, g.descricao_normalizada)].append(g)
    n = 0
    for m in sorted(novos, key=lambda m: (m.data_movimento, m.ordem_no_dia)):
        lst = pool.get((m.data_movimento, m.descricao_normalizada))
        if lst and m.categoria_id is None:
            g = lst.pop(0)  # várias linhas iguais no mesmo dia: usam-se pela ordem em que foram guardadas
            m.categoria_id, m.categoria_origem, m.atualizado_por = g.categoria_id, "manual", user_id
            db.delete(g)
            n += 1
    return n
