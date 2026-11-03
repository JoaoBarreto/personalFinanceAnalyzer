"""Leitor do .xls original do Bankinter: mesmas regras estritas do CSV, com montantes lidos EXATAMENTE."""

from decimal import Decimal as D

import pytest
from sqlalchemy import select

from app.models import Importacao
from app.parsers.banks.bankinter.csv_export import BankinterCsvParser
from app.parsers.banks.bankinter.parser import BankinterParser
from app.parsers.base import ParseError

from .conftest import N_LINHAS, SALDO_FINAL, SALDO_INICIAL, build_csv, build_xls
from .test_imports import confirm, up

parser = BankinterParser()


def _recusa(raw: bytes) -> str:
    with pytest.raises(ParseError) as e:
        parser.parse(raw)
    msg = str(e.value)
    assert "não foi importado" in msg and "ficheiro .xls original" in msg
    return msg


def _tuplo(s):
    return (
        [(m.data_movimento, m.data_valor, m.descricao_original, m.montante, m.saldo_apos, m.ordem_no_dia) for m in s.movimentos],
        s.moeda, s.periodo_inicio, s.periodo_fim, s.ordem_ficheiro, s.saldo_inicial, s.saldo_final,
    )  # fmt: skip


def test_xls_e_csv_dos_mesmos_movimentos_dao_exatamente_o_mesmo():
    xls, csv_ = parser.parse(build_xls()), parser.parse(build_csv())
    assert _tuplo(xls) == _tuplo(csv_)
    assert len(xls.movimentos) == N_LINHAS and xls.reconciliado
    assert (xls.saldo_inicial, xls.saldo_final) == (SALDO_INICIAL, SALDO_FINAL)
    assert BankinterCsvParser().can_parse(build_csv()) == 1.0 and parser.can_parse(build_xls()) == 1.0


def test_montantes_sao_lidos_exatamente_onde_os_floats_falham():
    valores = [
        D("0.29"),
        D("1.15"),
        D("8.64"),
        D("-50.00"),
        D("-0.01"),
        D("38847.06"),
        D("1234567.89"),
        D("-668.14"),
    ]
    rows = [(f"{i + 1:02d}-10-2026", f"{i + 1:02d}-10-2026", f"M{i}", v) for i, v in enumerate(valores)]
    s = parser.parse(build_xls(rows, saldo_inicial=D("38000.00")))
    assert [m.montante for m in s.movimentos] == valores  # Decimals idênticos, sem ruído de float
    assert s.saldo_final == D("38000.00") + sum(valores) and s.reconciliado
    assert all(m.montante == m.montante.quantize(D("0.01")) for m in s.movimentos)


def test_cabecalho_unido_e_rodape_nao_atrapalham():
    s = parser.parse(
        build_xls()
    )  # o gerador tem células unidas no preâmbulo e no rodapé, como o ficheiro real
    assert s.moeda == "EUR" and s.periodo_inicio.isoformat() == "2026-10-01"


def test_datas_do_excel_sao_recusadas():
    msg = _recusa(build_xls(datas_do_excel=True))
    assert "data do Excel" in msg and "guardado por outra aplicação" in msg and "linha 9" in msg


def test_montantes_em_texto_sao_recusados():
    msg = _recusa(build_xls(montantes_em_texto=True))
    assert "não é um número" in msg and f"{N_LINHAS} ocorrência(s)" in msg


def test_mais_de_duas_casas_decimais_sao_recusadas():
    assert "mais de 2 casas decimais" in _recusa(build_xls(casas=3))


def test_mais_de_uma_folha_e_recusado():
    assert "2 folhas" in _recusa(build_xls(folhas=2))


def test_colunas_alteradas_sao_recusadas():
    cab = [
        "Data Movimento",
        "Data Valor",
        "Descrição",
        "Transacção",
        "Valor",
        "Moeda",
        "Saldo",
        "Taxa Câmbio",
        "Data Taxa Câmbio",
    ]
    msg = _recusa(build_xls(cabecalho=cab))
    assert "Esperado:" in msg and "Encontrado:" in msg


def test_xlsx_html_e_lixo_com_extensao_xls_sao_recusados():
    assert "xlsx" in _recusa(b"PK\x03\x04" + b"0" * 50)
    _recusa(b"<html><body><table><tr><td>Data Movimento</td></tr></table></body></html>")
    assert "Não foi possível ler" in _recusa(bytes.fromhex("d0cf11e0a1b11ae1") + b"lixo" * 100)


def test_dois_formatos_do_mesmo_extrato_nao_duplicam_e_o_api_aceita_xls(api, db):
    def preview_xls(raw):
        return api.post(
            "/api/imports/preview",
            data={"conta_id": api.conta_id},
            files={"file": ("ConsultaMovimentos.xls", raw, "application/vnd.ms-excel")},
        )

    r = preview_xls(build_xls())
    assert r.status_code == 200 and r.json()["reconciliado"] is True
    assert r.json()["resumo"]["novo"] == N_LINHAS
    assert confirm(api, r.json()["id"]).json()["n_movimentos"] == N_LINHAS
    # o mesmo extrato em CSV, depois do .xls: tudo duplicado, sem avisos
    p = up(api, build_csv()).json()
    assert p["resumo"] == {"novo": 0, "duplicado": N_LINHAS, "possivel_duplicado": 0} and p["avisos"] == []
    # e o .xls repetido é recusado como o mesmo ficheiro
    assert preview_xls(build_xls()).status_code == 409


def test_upload_rejeita_xlsx_e_pdf_com_mensagem(api):
    for raw, frase in ((b"PK\x03\x04xx", ".xlsx"), (b"%PDF-1.7", "PDF")):
        r = api.post(
            "/api/imports/preview",
            data={"conta_id": api.conta_id},
            files={"file": ("x", raw, "application/octet-stream")},
        )
        assert r.status_code == 415 and frase in r.json()["detail"] and ".xls" in r.json()["detail"]


def test_xls_com_defeitos_fica_em_erro_e_nao_grava(api, db):
    r = api.post(
        "/api/imports/preview",
        data={"conta_id": api.conta_id},
        files={"file": ("x.xls", build_xls(datas_do_excel=True), "application/vnd.ms-excel")},
    )
    assert r.status_code == 422 and "data do Excel" in r.json()["detail"]
    assert db.scalars(select(Importacao)).one().estado == "erro"
