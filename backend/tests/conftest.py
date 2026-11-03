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


EXPECTED = (
    "Data Movimento", "Data Valor", "Descrição", "Transacção", "Montante", "Moeda", "Saldo",
    "Taxa Câmbio", "Data Taxa Câmbio",
)  # fmt: skip
ESTILOS = ("virgula", "ponto", "virgula_milhares", "ponto_milhares")


def _num(x: D, estilo: str = "virgula") -> str:
    """Formata como o homebanking: «1234,56», «1234.56», «1.234,56» ou «1,234.56»."""
    base = f"{x:,.2f}" if estilo.endswith("_milhares") else f"{x:.2f}"  # 1,234.56 | 1234.56
    if estilo.startswith("virgula"):
        base = base.replace(",", "\0").replace(".", ",").replace("\0", ".")
    return f'"{base}"'


def _pt(x: D) -> str:
    return _num(x, "virgula")


def _periodo(rows) -> str:
    """Como o homebanking: o período pedido cobre os meses inteiros das datas do extrato."""
    import calendar
    from datetime import datetime

    datas = [datetime.strptime(r[0], "%d-%m-%Y") for r in rows]
    a, b = min(datas), max(datas)
    return f"01-{a:%m-%Y} a {calendar.monthrange(b.year, b.month)[1]:02d}-{b:%m-%Y}"


def build_csv(rows=None, saldo_inicial=SALDO_INICIAL, estilo="virgula") -> bytes:
    rows = ROWS if rows is None else rows
    lines = [
        ",,,,,,,,",
        "[Financial Institution],,,,,,,,",
        " ,,,,,,,,",
        "Nº de Conta à Ordem: [ACCT_REDACTED] ( EUR) - [Individual_1]  ,,,,,,,,",
        " ,,,,,,,,",
        f"Movimentos no período: {_periodo(rows)},,,,,,,,",
        " ,,,,,,,,",
        "Data Movimento,Data Valor,Descrição,Transacção,Montante,Moeda,Saldo,Taxa Câmbio,Data Taxa Câmbio",
    ]
    saldo = saldo_inicial
    for dm, dv, desc, m in rows:
        saldo += m
        d = f'"{desc}"' if "," in desc else desc
        lines.append(f"{dm},{dv},{d},-,{_num(m, estilo)},EUR,{_num(saldo, estilo)},-,-")
    lines += [
        " ,,,,,,,,",
        '"Conforme condições definidas em Preçário, disponível online. Texto legal, com vírgulas.",,,,,,,,',
    ]
    assert rows is not ROWS or saldo == SALDO_FINAL
    return "\n".join(lines).encode("utf-8")


def build_xls(
    rows=None,
    saldo_inicial=SALDO_INICIAL,
    *,
    datas_do_excel=False,
    montantes_em_texto=False,
    casas=2,
    folhas=1,
    cabecalho=None,
) -> bytes:
    """.xls sintético com a estrutura REAL do export do Bankinter (confirmada no ficheiro do utilizador):
    1 folha, preâmbulo na coluna A (com células unidas), cabeçalho na linha 8, datas em texto, Montante/Saldo
    numéricos (formato 0.00), linha em branco e rodapé unido. Os parâmetros produzem desvios para os testes."""
    import datetime

    import xlwt

    rows = ROWS if rows is None else rows
    wb = xlwt.Workbook()
    ws = wb.add_sheet("Sheet0")
    num = xlwt.easyxf(num_format_str="0.00")
    datef = xlwt.easyxf(num_format_str="DD-MM-YYYY")
    ws.write_merge(1, 1, 0, 8, "[Financial Institution]")
    ws.write_merge(3, 3, 0, 8, "Nº de Conta à Ordem: [ACCT_REDACTED] ( EUR) - [Individual_1]")
    ws.write_merge(5, 5, 0, 8, f"Movimentos no período: {_periodo(rows)}")
    for c, h in enumerate(cabecalho or EXPECTED):
        ws.write(7, c, h)
    saldo = saldo_inicial
    for i, (dm, dv, desc, m) in enumerate(rows):
        r = 8 + i
        saldo += m
        for c, v in ((0, dm), (1, dv)):
            if datas_do_excel:
                ws.write(r, c, datetime.datetime.strptime(v, "%d-%m-%Y").date(), datef)
            else:
                ws.write(r, c, v)
        ws.write(r, 2, desc)
        ws.write(r, 3, "-")
        for c, v in ((4, m), (6, saldo)):
            if montantes_em_texto:
                ws.write(r, c, f"{v:.2f}".replace(".", ","))
            elif casas != 2:
                ws.write(r, c, float(v) + 0.005 if c == 4 else float(v), num)  # 3.ª casa decimal
            else:
                ws.write(r, c, float(v), num)
        ws.write(r, 5, "EUR")
        ws.write(r, 7, "-")
        ws.write(r, 8, "-")
    fim = 8 + len(rows)
    ws.write(fim, 0, "")
    ws.write_merge(
        fim + 1, fim + 1, 0, 8, "Conforme condições definidas em Preçário, disponível online. Texto legal."
    )
    for k in range(2, folhas + 1):
        wb.add_sheet(f"Extra{k}")
    import io

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


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
