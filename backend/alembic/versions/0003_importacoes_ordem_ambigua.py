"""importacoes.ordem_ambigua

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("importacoes", sa.Column("ordem_ambigua", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("importacoes", "ordem_ambigua")
