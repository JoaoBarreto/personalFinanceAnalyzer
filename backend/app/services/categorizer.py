"""Motor de categorização (PRD 3.5): regras do utilizador, depois match exato no histórico.

O fuzzy e o classificador ML são Fase 2. Uma categorização manual nunca é sobrescrita.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Categoria, Conta, Movimento, Regra

SPECIFICITY = {"igual": 3, "comeca_por": 2, "contem": 1, "regex": 0}


@dataclass(frozen=True)
class RuleData:
    id: int | None
    padrao: str
    tipo_match: str
    categoria_id: int
    direcao: str = "ambos"
    montante_min: Decimal | None = None
    montante_max: Decimal | None = None
    conta_id: int | None = None
    prioridade: int = 100

    @staticmethod
    def of(r: Regra) -> RuleData:
        return RuleData(
            r.id,
            r.padrao,
            r.tipo_match,
            r.categoria_id,
            r.direcao,
            r.montante_min,
            r.montante_max,
            r.conta_id,
            r.prioridade,
        )


def rule_matches(rule: RuleData, desc_norm: str, montante: Decimal, conta_id: int) -> bool:
    if rule.conta_id is not None and rule.conta_id != conta_id:
        return False
    if rule.direcao == "debito" and montante >= 0:
        return False
    if rule.direcao == "credito" and montante <= 0:
        return False
    absoluto = abs(montante)
    if rule.montante_min is not None and absoluto < rule.montante_min:
        return False
    if rule.montante_max is not None and absoluto > rule.montante_max:
        return False
    t, p = rule.tipo_match, rule.padrao
    if t == "contem":
        return p in desc_norm
    if t == "comeca_por":
        return desc_norm.startswith(p)
    if t == "igual":
        return desc_norm == p
    if t == "regex":
        try:
            return re.search(p, desc_norm, re.IGNORECASE) is not None
        except re.error:
            return False
    return False


def _rank(r: RuleData):
    # Desempate (PRD 3.5): maior prioridade; tipo mais específico; padrão mais longo; regra mais antiga
    return (-r.prioridade, -SPECIFICITY[r.tipo_match], -len(r.padrao), r.id if r.id is not None else 10**18)


def best_rule(rules: list[RuleData], desc_norm: str, montante: Decimal, conta_id: int) -> RuleData | None:
    hits = [r for r in rules if rule_matches(r, desc_norm, montante, conta_id)]
    return min(hits, key=_rank) if hits else None


def load_rules(db: Session, dono_id: int) -> list[RuleData]:
    return [
        RuleData.of(r)
        for r in db.scalars(select(Regra).where(Regra.ativa.is_(True), Regra.dono_id == dono_id))
    ]


def owned_movements(dono_id: int):
    """Condição: movimento numa conta do utilizador."""
    return Movimento.conta_id.in_(select(Conta.id).where(Conta.dono_id == dono_id))


def history_map(db: Session, dono_id: int) -> dict[str, int]:
    """descricao_normalizada -> categoria mais frequente (desempate: a mais recente) escolhida À MÃO.

    Só contam as escolhas manuais: as categorias vindas de regras já estão nas regras, e se contassem aqui, uma
    categorização antiga de uma regra editada voltava a ser sugerida pelo histórico (circular).
    """
    q = (
        select(Movimento.descricao_normalizada, Movimento.categoria_id, func.count(), func.max(Movimento.id))
        .where(Movimento.categoria_origem == "manual", owned_movements(dono_id))
        .group_by(Movimento.descricao_normalizada, Movimento.categoria_id)
    )
    best: dict[str, tuple[int, int, int]] = {}
    for desc, cat, n, last in db.execute(q):
        if desc not in best or (n, last) > best[desc][:2]:
            best[desc] = (n, last, cat)
    return {d: v[2] for d, v in best.items()}


@dataclass
class CategorizeResult:
    applied: dict[int, int]  # regra_id -> nº de linhas atribuídas
    released: int = (
        0  # linhas que voltaram a «por categorizar» porque a regra que as categorizou já não se aplica
    )


def categorize(
    db: Session,
    movs: list[Movimento],
    dono_id: int,
    *,
    only_uncategorized: bool,
    rules: list[RuleData] | None = None,
) -> CategorizeResult:
    """Aplica regras e depois histórico (escolhas manuais). Ignora sempre `manual`.

    Na reaplicação total (`only_uncategorized=False`), uma linha categorizada por uma regra que entretanto foi
    editada ou desativada, e que já não a apanha, é libertada (volta a «por categorizar»). As linhas cuja regra foi
    APAGADA (regra_id nulo) mantêm a categoria.
    """
    rules = load_rules(db, dono_id) if rules is None else rules
    hist = history_map(db, dono_id)
    applied: Counter[int] = Counter()
    released = 0
    for m in movs:
        if m.categoria_origem == "manual":
            continue
        if only_uncategorized and m.categoria_id is not None:
            continue
        r = best_rule(rules, m.descricao_normalizada, m.montante, m.conta_id)
        if r is not None:
            if (m.categoria_id, m.categoria_origem, m.regra_id) != (r.categoria_id, "regra", r.id):
                m.categoria_id, m.categoria_origem, m.regra_id = r.categoria_id, "regra", r.id
                applied[r.id] += 1
        elif m.categoria_origem == "regra" and m.regra_id is not None and not only_uncategorized:
            m.categoria_id = m.categoria_origem = m.regra_id = None
            released += 1
        elif m.categoria_id is None and (cat := hist.get(m.descricao_normalizada)) is not None:
            m.categoria_id, m.categoria_origem, m.regra_id = cat, "historico", None
    for rid, n in applied.items():
        db.execute(
            Regra.__table__.update().where(Regra.id == rid).values(n_aplicacoes=Regra.n_aplicacoes + n)
        )
    return CategorizeResult(dict(applied), released)


def impact(db: Session, rule: RuleData, dono_id: int, linhas: int = 0) -> dict:
    """Movimentos não-manuais que a regra passaria a categorizar (manuais nunca entram na contagem).

    Com `linhas > 0` devolve também as primeiras `linhas` (para o utilizador as ver e validar antes de aplicar).
    """
    others = [r for r in load_rules(db, dono_id) if r.id != rule.id]
    candidates = others + [rule]
    afetados = conflitos = 0
    out: list[dict] = []
    nomes = (
        {c.id: c.nome for c in db.scalars(select(Categoria).where(Categoria.dono_id == dono_id))}
        if linhas
        else {}
    )
    q = select(Movimento).where(
        Movimento.categoria_origem.is_distinct_from("manual"), owned_movements(dono_id)
    )
    q = q.order_by(Movimento.data_movimento, Movimento.ordem_no_dia, Movimento.id)
    for m in db.scalars(q):
        w = best_rule(candidates, m.descricao_normalizada, m.montante, m.conta_id)
        if w is None or w is not rule:
            continue
        if (m.categoria_id, m.categoria_origem, m.regra_id) == (rule.categoria_id, "regra", rule.id):
            continue
        afetados += 1
        conflito = m.categoria_id is not None and m.categoria_id != rule.categoria_id
        conflitos += conflito
        if linhas and len(out) < linhas:
            out.append(
                {
                    "id": m.id,
                    "data_movimento": m.data_movimento,
                    "descricao_original": m.descricao_original,
                    "descricao_normalizada": m.descricao_normalizada,
                    "montante": str(m.montante),
                    "categoria_atual": nomes.get(m.categoria_id),
                    "conflito": conflito,
                }
            )
    res: dict = {"afetados": afetados, "conflitos": conflitos}
    if linhas:
        res["linhas"] = out
        res["truncado"] = afetados > len(out)
    return res
