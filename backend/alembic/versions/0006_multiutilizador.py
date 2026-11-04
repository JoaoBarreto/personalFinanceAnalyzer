"""multiutilizador: cada conta, regra e categoria pertence a um utilizador (dono_id)

- contas.dono_id substitui titular_id (a conta conjunta deixa de existir); o nome da conta é único por dono.
- regras.dono_id e categorias.dono_id; categorias únicas por (dono, pai, nome).
- Movimentos, importações e categorizações guardadas herdam o dono pela conta.

Dados existentes: sem utilizadores (instalação nova) apagam-se as categorias do seed antigo (cada utilizador recebe
a sua cópia ao ser criado); com utilizadores, TUDO o que existe passa para o de menor id e os restantes recebem
categorias novas do seed. O downgrade repõe a estrutura (titular_id = dono) mas falha se houver nomes repetidos.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

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
    ("Poupança/Investimento", "transferencia", []),
]


def upgrade() -> None:
    conn = op.get_bind()
    for t in ("contas", "regras", "categorias"):
        op.add_column(t, sa.Column("dono_id", sa.BigInteger(), nullable=True))
        op.create_foreign_key(f"fk_{t}_dono", t, "utilizadores", ["dono_id"], ["id"], ondelete="CASCADE")
    # o índice antigo (pai, nome) impediria as categorias do segundo utilizador: sai antes de inserir
    op.drop_index("uq_categorias_parent_nome", table_name="categorias")
    users = [r[0] for r in conn.execute(sa.text("SELECT id FROM utilizadores ORDER BY id"))]
    if users:
        for t in ("contas", "regras", "categorias"):
            conn.execute(sa.text(f"UPDATE {t} SET dono_id = :u"), {"u": users[0]})
        ins = sa.text(
            "INSERT INTO categorias (nome, parent_id, tipo, dono_id) VALUES (:nome, :parent, :tipo, :dono) RETURNING id"
        )
        for outro in users[1:]:
            for pai, tipo, filhos in SEED:
                pid = conn.execute(
                    ins, {"nome": pai, "parent": None, "tipo": tipo, "dono": outro}
                ).scalar_one()
                for f in filhos:
                    conn.execute(ins, {"nome": f, "parent": pid, "tipo": tipo, "dono": outro})
    else:
        conn.execute(sa.text("DELETE FROM regras"))
        conn.execute(sa.text("DELETE FROM categorias WHERE parent_id IS NOT NULL"))
        conn.execute(sa.text("DELETE FROM categorias"))
    for t in ("contas", "regras", "categorias"):
        op.alter_column(t, "dono_id", nullable=False)
    op.drop_constraint("contas_nome_key", "contas", type_="unique")
    op.create_index("uq_contas_dono_nome", "contas", ["dono_id", "nome"], unique=True)
    op.create_index(
        "uq_categorias_dono_parent_nome",
        "categorias",
        ["dono_id", sa.literal_column("coalesce(parent_id, 0)"), "nome"],
        unique=True,
    )
    op.create_index("ix_regras_dono", "regras", ["dono_id"])
    op.drop_column("contas", "titular_id")


def downgrade() -> None:
    op.add_column("contas", sa.Column("titular_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key("contas_titular_id_fkey", "contas", "utilizadores", ["titular_id"], ["id"])
    op.execute("UPDATE contas SET titular_id = dono_id")
    op.drop_index("ix_regras_dono", table_name="regras")
    op.drop_index("uq_categorias_dono_parent_nome", table_name="categorias")
    op.create_index(
        "uq_categorias_parent_nome",
        "categorias",
        [sa.literal_column("coalesce(parent_id, 0)"), "nome"],
        unique=True,
    )
    op.drop_index("uq_contas_dono_nome", table_name="contas")
    op.create_unique_constraint("contas_nome_key", "contas", ["nome"])
    for t in ("categorias", "regras", "contas"):
        op.drop_constraint(f"fk_{t}_dono", t, type_="foreignkey")
        op.drop_column(t, "dono_id")
