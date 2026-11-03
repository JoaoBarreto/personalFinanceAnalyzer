"""Ciclo de vida da importação (PRD 3.2 e 4.2): preview -> confirm -> revert.

Os valores monetários vão para `staging` (JSONB) como strings e as datas como ISO, nunca como float.
Não se regista nenhuma descrição nem montante em logs.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Conta, Importacao, Movimento
from ..parsers.base import ParsedStatement, ParseError
from ..parsers.reconcile import chronological_breaks
from ..parsers.registry import get_parser
from .dedup import DedupResult, Row, deduplicate
from .normalizer import normalize

PREVIEW_TTL = timedelta(hours=24)


class ServiceError(Exception):
    def __init__(self, status_code: int, detail: Any):
        self.status_code, self.detail = status_code, detail


class Correcao(BaseModel):
    data_movimento: date | None = None
    data_valor: date | None = None
    descricao_original: str | None = Field(default=None, min_length=1)
    montante: Decimal | None = None
    saldo_apos: Decimal | None = None


class ConfirmIn(BaseModel):
    linhas_excluidas: list[int] = []
    correcoes: dict[int, Correcao] = {}
    # Possíveis duplicados NÃO são gravados por omissão; listar aqui os índices a gravar mesmo assim.
    incluir_possiveis_duplicados: list[int] = []


@dataclass
class Line:
    i: int
    data_movimento: date
    data_valor: date | None
    descricao_original: str
    montante: Decimal
    saldo_apos: Decimal | None
    ordem_no_dia: int


def _now() -> datetime:
    return datetime.now(UTC)


def _dump(line: Line, estado: str) -> dict[str, Any]:
    return {
        "i": line.i,
        "data_movimento": line.data_movimento.isoformat(),
        "data_valor": line.data_valor.isoformat() if line.data_valor else None,
        "descricao_original": line.descricao_original,
        "montante": str(line.montante),
        "saldo_apos": str(line.saldo_apos) if line.saldo_apos is not None else None,
        "ordem_no_dia": line.ordem_no_dia,
        "estado": estado,
    }


def _load(d: dict[str, Any]) -> Line:
    return Line(
        d["i"],
        date.fromisoformat(d["data_movimento"]),
        date.fromisoformat(d["data_valor"]) if d["data_valor"] else None,
        d["descricao_original"],
        Decimal(d["montante"]),
        Decimal(d["saldo_apos"]) if d["saldo_apos"] is not None else None,
        d["ordem_no_dia"],
    )


def _existing(db: Session, conta_id: int, d0: date, d1: date) -> list[Row]:
    q = select(Movimento.data_movimento, Movimento.montante, Movimento.saldo_apos).where(
        Movimento.conta_id == conta_id, Movimento.data_movimento.between(d0, d1)
    )
    return [Row(*r) for r in db.execute(q)]


def _classify(db: Session, conta_id: int, lines: list[Line]) -> DedupResult:
    d0, d1 = min(ln.data_movimento for ln in lines), max(ln.data_movimento for ln in lines)
    rows = [Row(ln.data_movimento, ln.montante, ln.saldo_apos) for ln in lines]
    return deduplicate(rows, _existing(db, conta_id, d0, d1))


def _reconcile(lines: list[Line]):
    """(saldo_inicial, saldo_final, diferenca, quebras) sobre TODAS as linhas, já com correções."""
    if any(ln.saldo_apos is None for ln in lines):
        raise ServiceError(422, "Existem linhas sem saldo; não é possível reconciliar.")
    pairs = [(ln.montante, ln.saldo_apos) for ln in lines]
    saldo_inicial = lines[0].saldo_apos - lines[0].montante
    saldo_final = lines[-1].saldo_apos
    diferenca = saldo_final - (saldo_inicial + sum((ln.montante for ln in lines), Decimal(0)))
    return saldo_inicial, saldo_final, diferenca, chronological_breaks(pairs)


def _estado_map(res: DedupResult) -> dict[int, str]:
    m = {i: "novo" for i in res.novos}
    m.update({i: "duplicado" for i in res.duplicados})
    m.update({i: "possivel_duplicado" for i in res.possiveis_duplicados})
    return m


def _s(x: Decimal | None) -> str | None:
    """Dinheiro na API sempre como string (o encoder do FastAPI converteria Decimal em float)."""
    return None if x is None else str(x)


def _view(imp: Importacao, lines: list[dict[str, Any]] | None, avisos: list[str]) -> dict[str, Any]:
    estados = [ln["estado"] for ln in lines or []]
    return {
        "id": imp.id,
        "conta_id": imp.conta_id,
        "estado": imp.estado,
        "ficheiro_nome": imp.ficheiro_nome,
        "periodo_inicio": imp.periodo_inicio,
        "periodo_fim": imp.periodo_fim,
        "saldo_inicial": _s(imp.saldo_inicial),
        "saldo_final": _s(imp.saldo_final),
        "reconciliado": imp.reconciliado,
        "diferenca": _s(imp.diferenca),
        "ordem_ficheiro": imp.ordem_ficheiro,
        "ordem_ambigua": imp.ordem_ambigua,
        "n_linhas_ficheiro": imp.n_linhas_ficheiro,
        "n_movimentos": imp.n_movimentos,
        "n_duplicados_ignorados": imp.n_duplicados_ignorados,
        "n_excluidos_utilizador": imp.n_excluidos_utilizador,
        "resumo": {k: estados.count(k) for k in ("novo", "duplicado", "possivel_duplicado")}
        if lines
        else None,
        "avisos": avisos,
        "linhas": lines,
        "expira_em": imp.expira_em,
    }


def get_view(db: Session, imp_id: int) -> dict[str, Any]:
    imp = db.get(Importacao, imp_id)
    if imp is None:
        raise ServiceError(404, "Importação não encontrada")
    lines = imp.staging["linhas"] if imp.staging else None
    return _view(imp, lines, imp.staging["avisos"] if imp.staging else [])


def preview(db: Session, conta_id: int, filename: str, content: bytes, user_id: int) -> dict[str, Any]:
    conta = db.get(Conta, conta_id)
    if conta is None or conta.arquivada:
        raise ServiceError(404, "Conta não encontrada")
    # limpeza oportunista de pré-visualizações expiradas (guardam descrições e montantes em staging)
    db.execute(delete(Importacao).where(Importacao.estado == "preview", Importacao.expira_em <= _now()))
    db.commit()
    fhash = hashlib.sha256(content).hexdigest()
    if db.scalar(
        select(Importacao.id).where(
            Importacao.conta_id == conta_id,
            Importacao.ficheiro_hash == fhash,
            Importacao.estado == "confirmada",
        )
    ):
        raise ServiceError(
            409, "Este ficheiro já foi importado nesta conta (reverta a importação para o repetir)."
        )

    parser = get_parser(conta.parser_id)

    def fail(msg: str) -> ServiceError:
        db.add(
            Importacao(
                conta_id=conta_id,
                ficheiro_nome=filename,
                ficheiro_hash=fhash,
                estado="erro",
                erro_detalhe=msg,
                criada_por=user_id,
            )
        )
        db.commit()
        return ServiceError(422, msg)

    if parser is None or parser.can_parse(content) < 0.5:
        raise fail("O ficheiro não corresponde ao formato esperado para esta conta.")
    try:
        st: ParsedStatement = parser.parse(content)
    except ParseError as e:
        raise fail(str(e)) from e

    lines = [
        Line(
            i, m.data_movimento, m.data_valor, m.descricao_original, m.montante, m.saldo_apos, m.ordem_no_dia
        )
        for i, m in enumerate(st.movimentos)
    ]
    res = _classify(db, conta_id, lines)
    estados = _estado_map(res)
    saldo_inicial, saldo_final, diferenca, quebras = _reconcile(lines)

    avisos: list[str] = []
    if st.ordem_ambigua:
        avisos.append(
            "Não foi possível determinar a ordem do ficheiro pela cadeia de saldos; assumida ascendente."
        )
    last = db.scalar(
        select(Movimento.saldo_apos)
        .where(Movimento.conta_id == conta_id, Movimento.data_movimento < lines[0].data_movimento)
        .order_by(Movimento.data_movimento.desc(), Movimento.ordem_no_dia.desc(), Movimento.id.desc())
        .limit(1)
    )
    if last is not None and last != saldo_inicial:
        avisos.append("O saldo inicial do ficheiro não coincide com o último saldo já gravado da conta.")
    if res.possiveis_duplicados:
        avisos.append("Há possíveis duplicados; por omissão não são gravados.")

    imp = Importacao(
        conta_id=conta_id,
        ficheiro_nome=filename,
        ficheiro_hash=fhash,
        estado="preview",
        periodo_inicio=st.periodo_inicio,
        periodo_fim=st.periodo_fim,
        saldo_inicial=saldo_inicial,
        saldo_final=saldo_final,
        reconciliado=not quebras,
        diferenca=diferenca,
        ordem_ficheiro=st.ordem_ficheiro,
        ordem_ambigua=st.ordem_ambigua,
        n_linhas_ficheiro=len(lines),
        criada_por=user_id,
        expira_em=_now() + PREVIEW_TTL,
    )
    dumped = [_dump(ln, estados[ln.i]) for ln in lines]
    imp.staging = {"linhas": dumped, "avisos": avisos}
    db.add(imp)
    db.commit()
    return _view(imp, dumped, avisos)


def confirm(db: Session, imp_id: int, body: ConfirmIn, user_id: int) -> dict[str, Any]:
    imp = db.scalar(select(Importacao).where(Importacao.id == imp_id).with_for_update())
    if imp is None:
        raise ServiceError(404, "Importação não encontrada")
    if imp.estado != "preview":
        raise ServiceError(409, f"A importação está no estado {imp.estado!r}.")
    if imp.expira_em and imp.expira_em <= _now():
        raise ServiceError(410, "A pré-visualização expirou; carregue o ficheiro de novo.")

    lines = [_load(d) for d in imp.staging["linhas"]]
    valid = {ln.i for ln in lines}
    excluded = set(body.linhas_excluidas)
    if not (excluded | set(body.correcoes) | set(body.incluir_possiveis_duplicados)) <= valid:
        raise ServiceError(422, "Índice de linha inválido.")
    for i, c in body.correcoes.items():
        for field, value in c.model_dump(exclude_none=True).items():
            setattr(lines[i], field, value)

    saldo_inicial, saldo_final, diferenca, quebras = _reconcile(lines)
    imp.saldo_inicial, imp.saldo_final, imp.diferenca, imp.reconciliado = (
        saldo_inicial,
        saldo_final,
        diferenca,
        not quebras,
    )
    if quebras:
        db.commit()  # fica em preview com a diferença visível
        raise ServiceError(
            422,
            {
                "mensagem": "Os saldos não reconciliam; corrija as linhas indicadas.",
                "diferenca": str(diferenca),
                "quebras": [
                    {"linha": q.index, "esperado": str(q.esperado), "encontrado": str(q.encontrado)}
                    for q in quebras
                ],
            },
        )

    if db.scalar(
        select(Importacao.id).where(
            Importacao.conta_id == imp.conta_id,
            Importacao.ficheiro_hash == imp.ficheiro_hash,
            Importacao.estado == "confirmada",
        )
    ):
        raise ServiceError(409, "Este ficheiro já foi importado nesta conta.")

    res = _classify(db, imp.conta_id, lines)  # volta a classificar: a BD ou as correções podem ter mudado
    include = set(body.incluir_possiveis_duplicados)
    to_insert = sorted(
        {i for i in res.novos if i not in excluded}
        | {i for i in res.possiveis_duplicados if i in include - excluded}
    )
    ignorados = [
        i for i in res.duplicados + res.possiveis_duplicados if i not in excluded and i not in to_insert
    ]

    for i in to_insert:
        ln = lines[i]
        if ln.montante == 0:
            raise ServiceError(422, f"A linha {i} tem montante 0.")
        db.add(
            Movimento(
                conta_id=imp.conta_id,
                importacao_id=imp.id,
                data_movimento=ln.data_movimento,
                data_valor=ln.data_valor,
                ordem_no_dia=ln.ordem_no_dia,
                descricao_original=ln.descricao_original,
                descricao_normalizada=normalize(ln.descricao_original),
                montante=ln.montante,
                saldo_apos=ln.saldo_apos,
                criado_por=user_id,
                atualizado_por=user_id,
            )
        )
    imp.estado, imp.confirmada_em = "confirmada", _now()
    imp.n_movimentos, imp.n_duplicados_ignorados = len(to_insert), len(ignorados)
    imp.n_excluidos_utilizador = len(excluded)
    imp.staging, imp.expira_em = None, None
    try:
        db.commit()
    except IntegrityError as e:  # corrida na unicidade (conta, hash) confirmada
        db.rollback()
        raise ServiceError(409, "Este ficheiro já foi importado nesta conta.") from e
    return _view(imp, None, [])


def revert_or_cancel(db: Session, imp_id: int, user_id: int) -> None:
    imp = db.scalar(select(Importacao).where(Importacao.id == imp_id).with_for_update())
    if imp is None:
        raise ServiceError(404, "Importação não encontrada")
    if imp.estado in ("preview", "erro"):  # cancelar
        db.delete(imp)
        db.commit()
        return
    if imp.estado != "confirmada":
        raise ServiceError(409, "A importação já foi revertida.")
    blocking = db.scalar(
        select(func.count())
        .select_from(Importacao)
        .where(
            Importacao.conta_id == imp.conta_id,
            Importacao.estado == "confirmada",
            # "posterior" = confirmada depois (as duplicadas pertencem à primeira a confirmar), não criada depois
            or_(
                Importacao.confirmada_em > imp.confirmada_em,
                and_(Importacao.confirmada_em == imp.confirmada_em, Importacao.id > imp.id),
            ),
            Importacao.periodo_inicio <= imp.periodo_fim,
            Importacao.periodo_fim >= imp.periodo_inicio,
        )
    )
    if blocking:
        raise ServiceError(
            409, "Existe uma importação posterior com período sobreposto; reverta primeiro por ordem inversa."
        )
    db.execute(delete(Movimento).where(Movimento.importacao_id == imp.id))
    imp.estado, imp.revertida_em, imp.revertida_por = "revertida", _now(), user_id
    imp.n_movimentos = 0
    db.commit()
