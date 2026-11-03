"""categorizacoes_guardadas: categorizações manuais que sobrevivem ao reset/reversão

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "categorizacoes_guardadas",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "conta_id", sa.BigInteger(), sa.ForeignKey("contas.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("data_movimento", sa.Date(), nullable=False),
        sa.Column("descricao_normalizada", sa.Text(), nullable=False),
        sa.Column("categoria_id", sa.BigInteger(), sa.ForeignKey("categorias.id"), nullable=False),
        sa.Column("criada_em", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_cat_guardadas_chave",
        "categorizacoes_guardadas",
        ["conta_id", "data_movimento", "descricao_normalizada"],
    )


def downgrade() -> None:
    op.drop_index("ix_cat_guardadas_chave", table_name="categorizacoes_guardadas")
    op.drop_table("categorizacoes_guardadas")
