"""Detetor: propõe um modelo a partir do ficheiro, verifica-o e devolve perguntas quando há ambiguidade."""

import io
from datetime import datetime
from decimal import Decimal as D

import pytest

from app.parsers.banks.bankinter.parser import BankinterParser
from app.parsers.generic.detector import detect, verify
from app.parsers.generic.parser import GenericParser
from app.parsers.generic.template import Template

from .conftest import ROWS, build_csv, build_xls
from .test_generic_parser import HEADER, csv_bytes, fmt_num, linhas, tuplo


def mov(st):
    return tuplo(st)[0]


def test_oraculo_o_detetor_reproduz_o_parser_do_bankinter_em_xls_e_csv():
    """Prova independente de todo o circuito: o modelo detetado lê o mesmo que o parser dedicado do Bankinter."""
    bk = BankinterParser()
    for conteudo in (build_xls(), build_csv()):
        r = detect(conteudo)
        assert r["ok"], r["motivo"]
        t = Template.model_validate(r["modelo"])
        assert mov(GenericParser(t).parse(conteudo)) == mov(bk.parse(conteudo))
        assert r["resumo"]["movimentos"] == len(ROWS) and r["amostra"]


def test_csv_ponto_e_virgula_cp1252_com_dd_mm_inequivoco():
    r = detect(csv_bytes(linhas()))
    assert r["ok"] and r["modelo"]["separador"] == ";" and r["modelo"]["codificacao"] == "cp1252"
    assert r["modelo"]["formato_data"] == "dd/mm/aaaa" and r["modelo"]["decimal"] == ","
    assert r["modelo"]["montante"] == "Montante" and r["modelo"]["saldo"] == "Saldo"


def test_milhares_e_ponto_decimal_sao_deduzidos():
    r = detect(csv_bytes(linhas(), sep="|", datefmt="%Y-%m-%d", decimal=".", milhares=","))
    assert r["ok"] and (r["modelo"]["decimal"], r["modelo"]["milhares"]) == (".", "virgula")
    assert r["modelo"]["formato_data"] == "aaaa-mm-dd"


def test_ordem_decrescente_e_debito_credito():
    h = ["Data", "Descrição", "Débito", "Crédito", "Saldo"]
    out = ["Extrato", ";".join(h)]
    for dm, _dv, desc, m, s in reversed(linhas()):
        deb, cred = (fmt_num(-m), "") if m < 0 else ("", fmt_num(m))
        out.append(";".join([dm.strftime("%d/%m/%Y"), desc, deb, cred, fmt_num(s)]))
    c = ("\r\n".join(out) + "\r\n").encode("cp1252")
    assert detect(c)["perguntas"][0]["id"] == "formato_data"  # todos os dias <= 12: o detetor pergunta
    r = detect(c, {"formato_data": "dd/mm/aaaa"})
    assert r["ok"], r["motivo"]
    assert (r["modelo"]["debito"], r["modelo"]["credito"], r["resumo"]["ordem"]) == (
        "Débito",
        "Crédito",
        "desc",
    )


def test_xlsx_com_datas_nativas():
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Extrato"])
    ws.append(HEADER)
    for dm, dv, desc, m, s in linhas():
        ws.append([dm, dv, desc, float(m), float(s)])
    buf = io.BytesIO()
    wb.save(buf)
    r = detect(buf.getvalue())
    assert r["ok"] and r["modelo"]["celulas_data_nativas"] is True and r["modelo"]["formato"] == "xlsx"


def test_dia_mes_ambiguo_volta_como_pergunta_e_resolve_com_a_resposta():
    # todas as datas com dia <= 12: dd/mm e mm/dd são ambos válidos
    rows = [
        (datetime(2026, 3, d), datetime(2026, 3, d), f"MOV {d}", D("-5.00"), D(1000 - 5 * d) + D("0.00"))
        for d in (1, 2, 3, 4)
    ]
    c = csv_bytes(rows)
    r = detect(c)
    assert not r["ok"] and [p["id"] for p in r["perguntas"]] == ["formato_data"]
    assert {o["valor"] for o in r["perguntas"][0]["opcoes"]} == {"dd/mm/aaaa", "mm/dd/aaaa"}
    r2 = detect(c, {"formato_data": "dd/mm/aaaa"})
    assert r2["ok"] and r2["modelo"]["formato_data"] == "dd/mm/aaaa"
    assert r2["resumo"]["periodo"][0] == "2026-03-01"


def test_sem_coluna_de_saldo_ou_sem_cadeia_nao_propoe_nada():
    c = csv_bytes(linhas()).replace(b";Saldo", b";Extra").replace(b"1027,01", b"1,00")  # cadeia partida
    r = detect(c)
    assert not r["ok"] and r["modelo"] is None and "saldo" in r["motivo"].lower()
    sem_saldo = "\r\n".join(
        [
            "Extrato",
            "Data;Descrição;Montante",
            *[f"{d.strftime('%d/%m/%Y')};{x};{fmt_num(m)}" for d, _v, x, m, _s in linhas()],
        ]
    )
    assert not detect(sem_saldo.encode("cp1252"))["ok"]


def test_recusa_pdf_html_e_lixo():
    assert not detect(b"%PDF-1.7 x")["ok"] and not detect(b"<html></html>")["ok"]
    assert not detect(b"isto nao e um extrato\nnem tem colunas")["ok"]


def test_verify_recusa_modelo_editado_que_nao_bate_e_aceita_o_correto():
    c = csv_bytes(linhas())
    m = detect(c)["modelo"]
    assert verify(c, m)["ok"]
    assert not verify(c, {**m, "decimal": "."})["ok"]  # o caso «-889.50»
    assert not verify(c, {**m, "saldo": "Montante", "montante": "Saldo"})["ok"]
    assert "inválido" in verify(c, {**m, "extra": 1})["motivo"]


def test_amostra_mostra_o_texto_original_ao_lado_do_valor_lido():
    r = detect(csv_bytes(linhas(), milhares=" "))
    a = r["amostra"][0]
    assert a["bruto"]["Data"] == "01/10/2026" and a["lido"]["data"] == "2026-10-01"
    assert a["bruto"]["Montante"] == "900,00" and a["lido"]["montante"] == "900.00"


def test_endpoints_detect_e_verify_e_criacao_de_conta_ponta_a_ponta(api, db):
    import json

    c = csv_bytes(linhas())
    r = api.post("/api/banks/detect", files={"file": ("x.csv", c, "text/csv")})
    assert r.status_code == 200 and r.json()["ok"]
    modelo = r.json()["modelo"]
    v = api.post(
        "/api/banks/verify", data={"modelo": json.dumps(modelo)}, files={"file": ("x.csv", c, "text/csv")}
    )
    assert v.json()["ok"]
    bad = api.post(
        "/api/banks/verify",
        data={"modelo": json.dumps({**modelo, "decimal": "."})},
        files={"file": ("x.csv", c, "text/csv")},
    )
    assert bad.status_code == 200 and not bad.json()["ok"]
    conta = api.post(
        "/api/accounts",
        json={"nome": "Novo", "banco": "Banco Y", "parser_id": "generico", "config_importacao": modelo},
    )
    assert conta.status_code == 201
    pre = api.post(
        "/api/imports/preview",
        data={"conta_id": conta.json()["id"]},
        files={"file": ("x.csv", c, "text/csv")},
    )
    assert pre.status_code == 200 and pre.json()["reconciliado"]
    assert (
        api.post("/api/banks/detect", files={"file": ("x.pdf", b"%PDF-1.7 x", "application/pdf")}).json()[
            "ok"
        ]
        is False
    )
    assert (
        api.post(
            "/api/banks/detect", data={"respostas": "[1]"}, files={"file": ("x.csv", c, "text/csv")}
        ).status_code
        == 422
    )
