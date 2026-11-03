from datetime import date
from decimal import Decimal as D

import pytest

from app.parsers.banks.bankinter.csv_export import BankinterCsvParser
from app.parsers.base import ParseError

from .conftest import N_LINHAS, SALDO_FINAL, SALDO_INICIAL, build_csv

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


# --- Robustez a variações do ficheiro exportado --------------------------------------------------


def _same_as_baseline(raw: bytes, content: bytes):
    base, got = parser.parse(content), parser.parse(raw)
    assert [(m.data_movimento, m.montante, m.saldo_apos, m.descricao_original) for m in got.movimentos] == [
        (m.data_movimento, m.montante, m.saldo_apos, m.descricao_original) for m in base.movimentos
    ]
    assert (
        got.reconciliado and got.saldo_inicial == base.saldo_inicial and got.saldo_final == base.saldo_final
    )


def test_quebras_de_linha_windows(content):
    _same_as_baseline(content.replace(b"\n", b"\r\n"), content)


def test_bom_utf8(content):
    _same_as_baseline(b"\xef\xbb\xbf" + content, content)


def test_separador_ponto_e_virgula(content):
    import csv
    import io

    rows = list(csv.reader(io.StringIO(content.decode())))
    out = io.StringIO()
    csv.writer(out, delimiter=";", lineterminator="\n").writerows(rows)
    _same_as_baseline(out.getvalue().encode(), content)


def test_milhares_com_ponto(content):
    import re

    text = re.sub(r'"(-?)(\d{1,3})(\d{3}),(\d\d)"', r'"\1\2.\3,\4"', content.decode())
    assert '"2.380,91"' in text  # a variante foi mesmo aplicada
    _same_as_baseline(text.encode(), content)


def test_linhas_de_cabecalho_a_mais_e_sem_rodape(content):
    lines = content.decode().splitlines()
    cut = next(i for i, l in enumerate(lines) if l.startswith(" ,,,") and i > 8)  # antes do rodapé
    raw = "\n".join(["Extra 1,,,,,,,,", "Extra 2,,,,,,,,", "Extra 3,,,,,,,,", *lines[:cut]]).encode()
    _same_as_baseline(raw, content)


def test_so_cabecalho_ou_vazio(content):
    header_only = b"\n".join(content.split(b"\n")[:8])
    for raw in (header_only, b"", b"\n\n\n"):
        with pytest.raises(ParseError):
            parser.parse(raw)


def test_linha_truncada_da_erro_claro(content):
    lines = content.decode().split("\n")
    i = next(k for k, l in enumerate(lines) if l.startswith("02-10-2026"))
    lines[i] = "02-10-2026,02-10-2026"
    with pytest.raises(ParseError, match="Linha"):
        parser.parse("\n".join(lines).encode())


def test_numero_invalido_da_erro_claro(content):
    bad = content.replace(b'"-2,25"', b'"abc"', 1)
    with pytest.raises(ParseError):
        parser.parse(bad)


# --- Separador decimal: ponto ou vírgula (regressão: «-889.50» lido como -88950) ------------------


def test_todos_os_estilos_numericos_dao_os_mesmos_valores(content_any):
    s = parser.parse(content_any)
    assert len(s.movimentos) == N_LINHAS and s.reconciliado
    assert (s.saldo_inicial, s.saldo_final) == (SALDO_INICIAL, SALDO_FINAL)
    assert sum(m.montante for m in s.movimentos) == D("2407.92")
    assert [m.montante for m in s.movimentos][:3] == [D("900.00"), D("-2.25"), D("-668.14")]


def test_regressao_valores_do_ecra_do_utilizador():
    from app.parsers.banks.bankinter.csv_export import _parse_amount, detect_number_style

    for raw, esperado in [
        ("-21.00", "-21.00"),
        ("32.82", "32.82"),
        ("-889.50", "-889.50"),
        ("2,380.91", "2380.91"),
    ]:
        style = detect_number_style([raw, "0.10"])
        assert style == "ponto" and _parse_amount(raw, style) == D(
            esperado
        )  # antes: -2100, 3282, -88950, 2.38091
    assert _parse_amount("-889,50", "virgula") == D("-889.50")


def test_ficheiro_com_ponto_decimal_nao_multiplica_por_100():
    rows = [
        ("05-01-2026", "05-01-2026", "PAG. IMPOSTOS", D("-221.54")),
        ("06-01-2026", "06-01-2026", "MEO", D("10.94")),
    ]
    s = parser.parse(build_csv(rows, saldo_inicial=D("1000.00"), estilo="ponto"))
    assert [m.montante for m in s.movimentos] == [D("-221.54"), D("10.94")]
    assert s.saldo_final == D("789.40") and s.reconciliado


def test_mistura_de_estilos_e_recusada(content):
    mixed = build_csv(estilo="ponto").replace(b'"-2.25"', b'"-2,25"', 1)
    with pytest.raises(ParseError, match="inconsistente"):
        parser.parse(mixed)


def test_valores_ambiguos_sem_decimais_sao_recusados():
    from app.parsers.banks.bankinter.csv_export import detect_number_style

    with pytest.raises(ParseError, match="ambíguos"):
        detect_number_style(["1.234", "-2.500"])
    assert detect_number_style(["100", "-50"]) == "virgula"  # inteiros simples: sem ambiguidade


def test_mais_de_duas_casas_decimais_e_agrupamento_invalido_sao_recusados():
    from app.parsers.banks.bankinter.csv_export import _parse_amount

    for style in ("virgula", "ponto"):
        for bad in ("2.38091", "2,38091", "12.34.5", "1,2345.00" if style == "ponto" else "1.2345,00"):
            with pytest.raises(ParseError):
                _parse_amount(bad, style)


def test_decisao_pelo_ultimo_separador():
    from app.parsers.banks.bankinter.csv_export import detect_number_style

    assert detect_number_style(["1.234.567,89"]) == "virgula"
    assert detect_number_style(["1,234,567.89"]) == "ponto"
    assert detect_number_style(["2,380.91"]) == "ponto" and detect_number_style(["2.380,91"]) == "virgula"
