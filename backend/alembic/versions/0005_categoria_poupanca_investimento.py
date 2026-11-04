"""categoria «Poupança/Investimento» (tipo transferência)

Dinheiro poupado que sai da conta (corretora, depósitos a prazo, certificados...). Não é despesa nem receita.

Revision ID: 0005
Revises: 0004
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO categorias (nome, parent_id, tipo) SELECT 'Poupança/Investimento', NULL, 'transferencia' "
        "WHERE NOT EXISTS (SELECT 1 FROM categorias WHERE nome = 'Poupança/Investimento')"
    )


def downgrade() -> None:
    # Só remove se não estiver em uso (a FK impede caso contrário).
    op.execute("DELETE FROM categorias WHERE nome = 'Poupança/Investimento' AND parent_id IS NULL")
