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


# --- Modelo estrito: tudo o que não seguir o export do Bankinter é RECUSADO com uma explicação --------


def _recusa(raw: bytes) -> str:
    with pytest.raises(ParseError) as e:
        parser.parse(raw)
    msg = str(e.value)
    assert "não foi importado" in msg and "sem o abrir e voltar a guardar" in msg  # diz o que fazer a seguir
    return msg


def test_ponto_decimal_e_recusado_e_mostra_o_valor_e_a_linha():
    """Regressão: «-889.50» era lido como -88950 e a reconciliação não o apanhava."""
    rows = [
        ("05-01-2026", "05-01-2026", "PAG. IMPOSTOS", D("-889.50")),
        ("06-01-2026", "06-01-2026", "MEO", D("32.82")),
    ]
    msg = _recusa(build_csv(rows, saldo_inicial=D("38000.00"), estilo="ponto"))
    assert "linha 9" in msg and "ponto como separador decimal" in msg and "-889.50" in msg  # 1.ª ocorrência


@pytest.mark.parametrize("estilo", ["ponto_milhares", "virgula_milhares"])
def test_separador_de_milhares_e_recusado(estilo):
    msg = _recusa(build_csv(estilo=estilo))
    assert "milhares" in msg or "ponto como separador decimal" in msg


def test_ponto_e_virgula_como_separador_de_campos_e_recusado(content):
    import csv
    import io

    rows = list(csv.reader(io.StringIO(content.decode())))
    out = io.StringIO()
    csv.writer(out, delimiter=";", lineterminator="\n").writerows(rows)
    assert "«;»" in _recusa(out.getvalue().encode())


def test_outra_codificacao_e_recusada(content):
    assert "UTF-8" in _recusa(content.decode().encode("cp1252"))


def test_colunas_diferentes_do_modelo_sao_recusadas(content):
    msg = _recusa(content.replace(b"Montante", b"Valor", 1))
    assert "Esperado:" in msg and "Encontrado:" in msg and "Valor" in msg


def test_falta_de_coluna_e_recusada(content):
    assert "colunas não correspondem" in _recusa(content.replace(",Data Taxa Câmbio".encode(), b"", 1))


@pytest.mark.parametrize("data", ["2026-10-02", "02/10/2026", "2-10-2026"])
def test_data_noutro_formato_e_recusada_e_nunca_trunca_em_silencio(content, data):
    bad = content.replace(b"02-10-2026,02-10-2026,DD SERVICO", f"{data},02-10-2026,DD SERVICO".encode(), 1)
    assert bad != content
    assert "formato inesperado" in _recusa(
        bad
    )  # sem isto, a linha seria tomada por rodapé e o resto perdia-se


def test_data_valor_invalida_e_recusada(content):
    bad = content.replace(b"02-10-2026,02-10-2026,DD SERVICO", b"02-10-2026,xx,DD SERVICO", 1)
    assert "Data Valor" in _recusa(bad)


@pytest.mark.parametrize(("antes", "depois", "frase"), [
    (b'"-2,25"', b'"-2,5"', "2 casas decimais"),
    (b'"-2,25"', b'"-2"', "2 casas decimais"),
    (b'"-2,25"', b'"abc"', "não é um valor numérico"),
    (b'"-2,25"', b'""', "em branco"),
])  # fmt: skip
def test_montantes_fora_do_modelo_sao_recusados(content, antes, depois, frase):
    assert frase in _recusa(content.replace(antes, depois, 1))


def test_moeda_diferente_e_recusada(content):
    assert "Moeda diferente de EUR" in _recusa(content.replace(b",EUR,", b",USD,", 1))


def test_linhas_fora_do_periodo_do_cabecalho_sao_recusadas(content):
    bad = content.replace(b"01-10-2026 a 31-10-2026", b"01-10-2026 a 02-10-2026")
    assert "fora do período" in _recusa(bad)


def test_problemas_iguais_sao_agrupados_com_contagem_e_primeira_ocorrencia():
    rows = [(f"{d:02d}-01-2026", f"{d:02d}-01-2026", f"M{d}", D("-1.50")) for d in range(1, 21)]
    msg = _recusa(build_csv(rows, estilo="ponto"))
    assert msg.count("• ") == 2  # Montante e Saldo: uma linha cada, não 40
    assert "20 ocorrência(s); primeira na linha 9" in msg


def test_o_modelo_original_continua_aceite_com_bom_e_crlf(content):
    parser.parse(b"\xef\xbb\xbf" + content.replace(b"\n", b"\r\n"))
