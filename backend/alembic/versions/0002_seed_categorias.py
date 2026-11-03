"""seed de categorias PT

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# (pai, tipo, [filhos]) - os filhos herdam o tipo do pai (PRD 3.7)
SEED = [
    ("Alimentação", "despesa", ["Supermercado", "Restaurantes", "Café e pastelaria"]),
    (
        "Casa",
        "despesa",
        [
            "Renda / Crédito habitação",
            "Eletricidade",
            "Água",
            "Gás",
            "Internet e telecomunicações",
            "Manutenção",
        ],
    ),
    (
        "Transportes",
        "despesa",
        ["Combustível", "Portagens", "Transportes públicos", "Parque e estacionamento"],
    ),
    ("Saúde", "despesa", ["Farmácia", "Consultas", "Seguros de saúde"]),
    ("Lazer", "despesa", ["Viagens", "Cultura e espetáculos", "Subscrições"]),
    ("Compras", "despesa", ["Vestuário", "Eletrónica", "Online"]),
    ("Seguros", "despesa", []),
    ("Impostos e taxas", "despesa", ["Imposto do selo", "IRS", "Comissões bancárias"]),
    ("Outras despesas", "despesa", []),
    ("Salário", "receita", []),
    ("Juros", "receita", []),
    ("Outras receitas", "receita", []),
    ("Transferências entre contas", "transferencia", []),
]


def upgrade() -> None:
    conn = op.get_bind()
    ins = sa.text(
        "INSERT INTO categorias (nome, parent_id, tipo) VALUES (:nome, :parent, :tipo) RETURNING id"
    )
    for pai, tipo, filhos in SEED:
        pid = conn.execute(ins, {"nome": pai, "parent": None, "tipo": tipo}).scalar_one()
        for f in filhos:
            conn.execute(ins, {"nome": f, "parent": pid, "tipo": tipo})


def downgrade() -> None:
    # Remove só categorias de seed ainda sem uso; se houver movimentos/regras, a FK impede e o downgrade falha.
    op.execute("DELETE FROM categorias WHERE parent_id IS NOT NULL")
    op.execute("DELETE FROM categorias WHERE parent_id IS NULL")
