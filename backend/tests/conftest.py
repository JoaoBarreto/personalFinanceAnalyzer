"""Fixture sintético: dados inventados com o mesmo layout do export Bankinter (sem dados pessoais)."""

import os
from decimal import Decimal as D
from pathlib import Path

import pytest

# Testes com BD: definir TEST_DATABASE_URL (Postgres descartável). Tem de ser antes de importar `app`.
TEST_DB = os.environ.get("TEST_DATABASE_URL")
if TEST_DB:
    os.environ["DATABASE_URL"] = TEST_DB
os.environ.setdefault("COOKIE_SECURE", "false")

# (data_movimento, data_valor, descricao, montante) em ordem cronológica
ROWS = [
    ("01-10-2026", "01-10-2026", "TRF A CREDITO SEPA+ - EMPRESA X", D("900.00")),
    ("01-10-2026", "30-09-2026", "COMPRA 0000000.30 LOJA A", D("-2.25")),
    ("01-10-2026", "01-10-2026", "EMPRESTIMO 0000-COB", D("-668.14")),
    ("02-10-2026", "02-10-2026", "DD SERVICO LUZ-0000", D("-72.82")),
    ("02-10-2026", "02-10-2026", "DD COOPERATIVA - COOP. DES. SUSTENTAVEL,", D("-69.53")),
    ("03-10-2026", "03-10-2026", "IMPOSTO DO SELO S/ COMISSÃO S/ TRF", D("-0.50")),
    ("05-10-2026", "05-10-2026", "COMPRA 0000000.36 SUPERMERCADO", D("-59.75")),
    ("10-10-2026", "10-10-2026", "TRF A CREDITO SEPA+ - SALARIO", D("2380.91")),
]
SALDO_INICIAL = D("1000.00")
N_LINHAS = len(ROWS)
SALDO_FINAL = D("3407.92")  # constante escrita à mão, para o teste não ser circular


def _pt(x: D) -> str:
    return f'"{x:.2f}"'.replace(".", ",")


def build_csv(rows=None, saldo_inicial=SALDO_INICIAL) -> bytes:
    rows = ROWS if rows is None else rows
    lines = [
        ",,,,,,,,",
        "[Financial Institution],,,,,,,,",
        " ,,,,,,,,",
        "Nº de Conta à Ordem: [ACCT_REDACTED] ( EUR) - [Individual_1]  ,,,,,,,,",
        " ,,,,,,,,",
        "Movimentos no período: 01-10-2026 a 31-10-2026,,,,,,,,",
        " ,,,,,,,,",
        "Data Movimento,Data Valor,Descrição,Transacção,Montante,Moeda,Saldo,Taxa Câmbio,Data Taxa Câmbio",
    ]
    saldo = saldo_inicial
    for dm, dv, desc, m in rows:
        saldo += m
        d = f'"{desc}"' if "," in desc else desc
        lines.append(f"{dm},{dv},{d},-,{_pt(m)},EUR,{_pt(saldo)},-,-")
    lines += [
        " ,,,,,,,,",
        '"Conforme condições definidas em Preçário, disponível online. Texto legal, com vírgulas.",,,,,,,,',
    ]
    assert rows is not ROWS or saldo == SALDO_FINAL
    return "\n".join(lines).encode("utf-8")


@pytest.fixture
def content() -> bytes:
    return build_csv()


@pytest.fixture(scope="session")
def migrated_db():
    if not TEST_DB:
        pytest.skip("defina TEST_DATABASE_URL para os testes com BD")
    from alembic.config import Config

    from alembic import command

    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(cfg, "head")


@pytest.fixture
def db(migrated_db):
    from sqlalchemy import text

    from app import rate_limit
    from app.db import SessionLocal

    rate_limit.reset()
    with SessionLocal() as s:
        s.execute(text("TRUNCATE utilizadores RESTART IDENTITY CASCADE"))
        s.commit()
        yield s


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def api(client):
    """Cliente autenticado (cookie + CSRF) com uma conta Bankinter criada."""
    from app.cli import create_user

    create_user("joao", "João", "uma-password-longa")
    r = client.post("/api/auth/login", json={"username": "joao", "password": "uma-password-longa"})
    client.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    c = client.post(
        "/api/accounts", json={"nome": "Ordenado", "banco": "Bankinter", "parser_id": "bankinter_csv"}
    )
    assert c.status_code == 201
    client.conta_id = c.json()["id"]
    return client
