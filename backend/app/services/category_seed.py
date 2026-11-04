"""Categorias iniciais (PT) que cada utilizador recebe como cópia própria ao ser criado.

Cada utilizador tem as suas categorias (renomear/desativar/apagar não afeta os outros). «Poupança/Investimento»
é do tipo transferência: dinheiro poupado que sai da conta, conta como poupado na taxa de poupança.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

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
    ("Poupança/Investimento", "transferencia", []),
]


def seed_categories(db: Session, dono_id: int) -> None:
    ins = text(
        "INSERT INTO categorias (nome, parent_id, tipo, dono_id) VALUES (:nome, :parent, :tipo, :dono) RETURNING id"
    )
    for pai, tipo, filhos in SEED:
        pid = db.execute(ins, {"nome": pai, "parent": None, "tipo": tipo, "dono": dono_id}).scalar_one()
        for f in filhos:
            db.execute(ins, {"nome": f, "parent": pid, "tipo": tipo, "dono": dono_id})
