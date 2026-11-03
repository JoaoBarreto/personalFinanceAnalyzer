"""Fixture sintético: dados inventados com o mesmo layout do export Bankinter (sem dados pessoais)."""

from decimal import Decimal as D

import pytest

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


def build_csv() -> bytes:
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
    saldo = SALDO_INICIAL
    for dm, dv, desc, m in ROWS:
        saldo += m
        d = f'"{desc}"' if "," in desc else desc
        lines.append(f"{dm},{dv},{d},-,{_pt(m)},EUR,{_pt(saldo)},-,-")
    lines += [
        " ,,,,,,,,",
        '"Conforme condições definidas em Preçário, disponível online. Texto legal, com vírgulas.",,,,,,,,',
    ]
    assert saldo == SALDO_FINAL
    return "\n".join(lines).encode("utf-8")


@pytest.fixture
def content() -> bytes:
    return build_csv()
