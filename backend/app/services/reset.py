"""Reposição dos dados importados, mantendo o trabalho de categorização.

Apaga TODOS os movimentos e importações (qualquer estado). Mantém utilizadores, contas, categorias e regras.
As categorizações feitas à mão são convertidas em regras «igual» (descrição normalizada -> categoria), para que
voltem a aplicar-se sozinhas quando o extrato for reimportado; as categorizações por regra já estão nas regras.
"""

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from ..models import Importacao, Movimento, Regra


def manual_choices(db: Session) -> list[tuple[str, int]]:
    """(descrição normalizada, categoria) escolhida à mão; se houver várias, a mais frequente (e mais recente)."""
    n = func.count().label("n")
    ultimo = func.max(Movimento.id).label("ultimo")
    q = (
        select(Movimento.descricao_normalizada, Movimento.categoria_id, n, ultimo)
        .where(Movimento.categoria_origem == "manual")
        .group_by(Movimento.descricao_normalizada, Movimento.categoria_id)
    )
    best: dict[str, tuple[int, int, int]] = {}
    for desc, cat, cnt, last in db.execute(q):
        if desc not in best or (cnt, last) > best[desc][:2]:
            best[desc] = (cnt, last, cat)
    return sorted((d, v[2]) for d, v in best.items())


def preview(db: Session) -> dict[str, int]:
    return {
        "movimentos": db.scalar(select(func.count()).select_from(Movimento)),
        "importacoes": db.scalar(select(func.count()).select_from(Importacao)),
        "categorizacoes_manuais": len(manual_choices(db)),
    }


def reset_movements(db: Session) -> dict[str, int]:
    existentes = {(r.padrao, r.tipo_match, r.categoria_id) for r in db.scalars(select(Regra))}
    novas = 0
    for desc, cat in manual_choices(db):
        if (desc, "igual", cat) in existentes:
            continue
        db.add(Regra(padrao=desc, tipo_match="igual", categoria_id=cat, origem="aprendida"))
        novas += 1
    movs = db.execute(delete(Movimento)).rowcount
    imps = db.execute(delete(Importacao)).rowcount
    db.execute(update(Regra).values(n_aplicacoes=0))
    db.commit()
    return {"movimentos_apagados": movs, "importacoes_apagadas": imps, "regras_criadas": novas}
