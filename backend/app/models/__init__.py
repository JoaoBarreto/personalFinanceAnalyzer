from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

TS = TIMESTAMP(timezone=True)
MONEY = Numeric(12, 2)


def _id() -> Mapped[int]:
    return mapped_column(BigInteger, Identity(always=True), primary_key=True)


class Utilizador(Base):
    __tablename__ = "utilizadores"
    id: Mapped[int] = _id()
    username: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    nome: Mapped[str] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    criado_em: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class Sessao(Base):
    __tablename__ = "sessoes"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    utilizador_id: Mapped[int] = mapped_column(ForeignKey("utilizadores.id", ondelete="CASCADE"))
    csrf_token: Mapped[str] = mapped_column(Text)
    criada_em: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    ultimo_uso_em: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    expira_em: Mapped[datetime] = mapped_column(TS)
    __table_args__ = (Index("ix_sessoes_expira_em", "expira_em"),)


class Conta(Base):
    __tablename__ = "contas"
    id: Mapped[int] = _id()
    nome: Mapped[str] = mapped_column(Text, unique=True)
    banco: Mapped[str] = mapped_column(Text)
    iban_mascarado: Mapped[str | None] = mapped_column(Text)
    moeda: Mapped[str] = mapped_column(String(3), server_default="EUR")
    parser_id: Mapped[str] = mapped_column(Text)
    config_importacao: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    titular_id: Mapped[int | None] = mapped_column(ForeignKey("utilizadores.id"))  # NULL = conjunta
    arquivada: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    criada_em: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class Importacao(Base):
    __tablename__ = "importacoes"
    id: Mapped[int] = _id()
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"))
    ficheiro_nome: Mapped[str] = mapped_column(Text)
    ficheiro_hash: Mapped[str] = mapped_column(String(64))
    estado: Mapped[str] = mapped_column(Text)
    periodo_inicio: Mapped[date | None] = mapped_column(Date)
    periodo_fim: Mapped[date | None] = mapped_column(Date)
    saldo_inicial: Mapped[Decimal | None] = mapped_column(MONEY)
    saldo_final: Mapped[Decimal | None] = mapped_column(MONEY)
    reconciliado: Mapped[bool | None] = mapped_column(Boolean)
    diferenca: Mapped[Decimal | None] = mapped_column(MONEY)
    ordem_ficheiro: Mapped[str | None] = mapped_column(Text)
    ordem_ambigua: Mapped[bool | None] = mapped_column(Boolean)
    n_linhas_ficheiro: Mapped[int] = mapped_column(Integer, server_default="0")
    n_movimentos: Mapped[int] = mapped_column(Integer, server_default="0")
    n_duplicados_ignorados: Mapped[int] = mapped_column(Integer, server_default="0")
    n_excluidos_utilizador: Mapped[int] = mapped_column(Integer, server_default="0")
    staging: Mapped[dict | None] = mapped_column(JSONB)
    expira_em: Mapped[datetime | None] = mapped_column(TS)
    erro_detalhe: Mapped[str | None] = mapped_column(Text)
    criada_por: Mapped[int | None] = mapped_column(ForeignKey("utilizadores.id"))
    criada_em: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    confirmada_em: Mapped[datetime | None] = mapped_column(TS)
    revertida_em: Mapped[datetime | None] = mapped_column(TS)
    revertida_por: Mapped[int | None] = mapped_column(ForeignKey("utilizadores.id"))
    __table_args__ = (
        CheckConstraint(
            "estado IN ('preview','confirmada','revertida','erro')", name="ck_importacoes_estado"
        ),
        CheckConstraint("ordem_ficheiro IN ('asc','desc')", name="ck_importacoes_ordem"),
        Index(
            "uq_importacoes_conta_hash_confirmada",
            "conta_id",
            "ficheiro_hash",
            unique=True,
            postgresql_where=text("estado = 'confirmada'"),
        ),
        Index("ix_importacoes_periodo", "conta_id", "periodo_inicio", "periodo_fim"),
    )


class Categoria(Base):
    __tablename__ = "categorias"
    id: Mapped[int] = _id()
    nome: Mapped[str] = mapped_column(Text)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categorias.id"))
    tipo: Mapped[str] = mapped_column(Text)
    cor: Mapped[str | None] = mapped_column(Text)
    icone: Mapped[str | None] = mapped_column(Text)
    ativa: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    __table_args__ = (
        CheckConstraint("tipo IN ('despesa','receita','transferencia')", name="ck_categorias_tipo"),
        Index("uq_categorias_parent_nome", func.coalesce(text("parent_id"), 0), "nome", unique=True),
    )


class Regra(Base):
    __tablename__ = "regras"
    id: Mapped[int] = _id()
    padrao: Mapped[str] = mapped_column(Text)
    tipo_match: Mapped[str] = mapped_column(Text, server_default="contem")
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"))
    direcao: Mapped[str] = mapped_column(Text, server_default="ambos")
    montante_min: Mapped[Decimal | None] = mapped_column(MONEY)
    montante_max: Mapped[Decimal | None] = mapped_column(MONEY)
    conta_id: Mapped[int | None] = mapped_column(ForeignKey("contas.id"))
    prioridade: Mapped[int] = mapped_column(Integer, server_default="100")
    origem: Mapped[str] = mapped_column(Text)
    ativa: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    n_aplicacoes: Mapped[int] = mapped_column(Integer, server_default="0")
    criado_por: Mapped[int | None] = mapped_column(ForeignKey("utilizadores.id"))
    atualizado_por: Mapped[int | None] = mapped_column(ForeignKey("utilizadores.id"))
    criada_em: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    atualizada_em: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    __table_args__ = (
        CheckConstraint("tipo_match IN ('contem','comeca_por','igual','regex')", name="ck_regras_tipo_match"),
        CheckConstraint("direcao IN ('debito','credito','ambos')", name="ck_regras_direcao"),
        CheckConstraint("origem IN ('manual','aprendida')", name="ck_regras_origem"),
        CheckConstraint(
            "montante_min IS NULL OR montante_max IS NULL OR montante_min <= montante_max",
            name="ck_regras_montante",
        ),
        Index("ix_regras_ativa_prioridade", "ativa", text("prioridade DESC")),
    )


class Movimento(Base):
    __tablename__ = "movimentos"
    id: Mapped[int] = _id()
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"))
    importacao_id: Mapped[int] = mapped_column(ForeignKey("importacoes.id", ondelete="RESTRICT"))
    data_movimento: Mapped[date] = mapped_column(Date)
    data_valor: Mapped[date | None] = mapped_column(Date)
    ordem_no_dia: Mapped[int] = mapped_column(SmallInteger)
    descricao_original: Mapped[str] = mapped_column(Text)
    descricao_normalizada: Mapped[str] = mapped_column(Text)
    montante: Mapped[Decimal] = mapped_column(MONEY)
    saldo_apos: Mapped[Decimal | None] = mapped_column(MONEY)
    categoria_id: Mapped[int | None] = mapped_column(ForeignKey("categorias.id"))
    categoria_origem: Mapped[str | None] = mapped_column(Text)
    regra_id: Mapped[int | None] = mapped_column(ForeignKey("regras.id", ondelete="SET NULL"))
    notas: Mapped[str | None] = mapped_column(Text)
    criado_por: Mapped[int | None] = mapped_column(ForeignKey("utilizadores.id"))
    atualizado_por: Mapped[int | None] = mapped_column(ForeignKey("utilizadores.id"))
    criada_em: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    atualizada_em: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    __table_args__ = (
        CheckConstraint("montante <> 0", name="ck_movimentos_montante"),
        CheckConstraint(
            "categoria_origem IN ('regra','historico','fuzzy','ml','manual')",
            name="ck_movimentos_categoria_origem",
        ),
        CheckConstraint(
            "(categoria_id IS NULL) = (categoria_origem IS NULL)", name="ck_movimentos_categoria_par"
        ),
        Index("ix_movimentos_dedup", "conta_id", "data_movimento", "montante"),  # NÃO único (PRD 4.1)
        Index("ix_movimentos_conta_data", "conta_id", "data_movimento"),
        Index("ix_movimentos_categoria", "categoria_id"),
        Index("ix_movimentos_desc_norm", "descricao_normalizada"),
        Index(
            "ix_movimentos_por_categorizar", "data_movimento", postgresql_where=text("categoria_id IS NULL")
        ),
        Index("ix_movimentos_importacao", "importacao_id"),
    )
