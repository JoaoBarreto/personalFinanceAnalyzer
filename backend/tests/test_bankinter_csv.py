from datetime import date
from decimal import Decimal as D

import pytest

from app.parsers.banks.bankinter.csv_export import BankinterCsvParser
from app.parsers.base import ParseError

from .conftest import N_LINHAS, SALDO_FINAL, SALDO_INICIAL

parser = BankinterCsvParser()


def test_valores_conhecidos(content):
    # Constantes escritas à mão (ver conftest), não derivadas do parser.
    s = parser.parse(content)
    assert len(s.movimentos) == N_LINHAS
    assert s.moeda == "EUR"
    assert (s.periodo_inicio, s.periodo_fim) == (date(2026, 10, 1), date(2026, 10, 31))
    assert s.ordem_ficheiro == "asc"
    assert s.saldo_inicial == SALDO_INICIAL
    assert s.saldo_final == SALDO_FINAL
    assert sum(m.montante for m in s.movimentos) == D("2407.92")
    assert s.reconciliado and s.diferenca == 0


def test_segunda_linha(content):
    m = parser.parse(content).movimentos[1]
    assert m.data_movimento == date(2026, 10, 1)
    assert m.data_valor == date(2026, 9, 30)
    assert m.montante == D("-2.25")
    assert m.saldo_apos == D("1897.75")


def test_ordem_no_dia(content):
    s = parser.parse(content)
    dia1 = [m for m in s.movimentos if m.data_movimento == date(2026, 10, 1)]
    assert [m.ordem_no_dia for m in dia1] == [0, 1, 2]


def test_descricao_com_virgula_entre_aspas(content):
    s = parser.parse(content)
    assert any(m.descricao_original.endswith("COOP. DES. SUSTENTAVEL,") for m in s.movimentos)


def test_rodape_nao_gera_movimentos(content):
    assert parser.parse(content).movimentos[-1].descricao_original == "TRF A CREDITO SEPA+ - SALARIO"


def _reverse(content: bytes) -> bytes:
    lines = content.decode().splitlines()
    first = next(i for i, l in enumerate(lines) if l[:2].isdigit())
    last = max(i for i, l in enumerate(lines) if l[:2].isdigit() and l[2] == "-")
    data = lines[first : last + 1][::-1]
    return "\n".join(lines[:first] + data + lines[last + 1 :]).encode()


def test_ficheiro_descendente(content):
    asc = parser.parse(content)
    desc = parser.parse(_reverse(content))
    assert desc.ordem_ficheiro == "desc"
    assert desc.reconciliado
    assert desc.saldo_inicial == asc.saldo_inicial and desc.saldo_final == asc.saldo_final
    assert [m.saldo_apos for m in desc.movimentos] == [m.saldo_apos for m in asc.movimentos]
    assert [m.ordem_no_dia for m in desc.movimentos] == [m.ordem_no_dia for m in asc.movimentos]


def test_corrupcao_de_um_centimo_e_detetada(content):
    bad = content.replace(b'"-2,25",EUR,"1897,75"', b'"-2,26",EUR,"1897,75"', 1)
    assert bad != content
    s = parser.parse(bad)
    assert not s.reconciliado
    assert s.quebras[0].index == 1
    assert s.quebras[0].esperado - s.quebras[0].encontrado == D("-0.01")


def test_cp1252(content):
    raw = content.decode().encode("cp1252")
    assert raw != content  # tem 'Ã' em COMISSÃO
    s = parser.parse(raw)
    assert len(s.movimentos) == N_LINHAS
    assert any("COMISSÃO" in m.descricao_original for m in s.movimentos)


def test_nao_bankinter():
    assert parser.can_parse(b"a,b,c\n1,2,3\n") == 0.0
    with pytest.raises(ParseError):
        parser.parse(b"a,b,c\n1,2,3\n")


def test_can_parse(content):
    assert parser.can_parse(content) == 1.0
