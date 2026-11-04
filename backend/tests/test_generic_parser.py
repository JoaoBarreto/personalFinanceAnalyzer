"""Parser genérico guiado por modelo: aceita vários estilos de extrato e recusa tudo o que não bate com o modelo."""

import io
from datetime import datetime
from decimal import Decimal as D

import pytest
from pydantic import ValidationError

from app.parsers.banks.bankinter.parser import BankinterParser
from app.parsers.base import ParseError
from app.parsers.generic.parser import GenericParser
from app.parsers.generic.template import Template

from .conftest import ROWS, SALDO_INICIAL, build_csv

HEADER = ["Data", "Data valor", "Descrição", "Montante", "Saldo"]


def linhas():
    """(data, data_valor, descrição, montante, saldo) cronológicas, a partir das linhas sintéticas do Bankinter."""
    saldo, out = SALDO_INICIAL, []
    for dm, dv, desc, m in ROWS:
        saldo += m
        out.append((datetime.strptime(dm, "%d-%m-%Y"), datetime.strptime(dv, "%d-%m-%Y"), desc, m, saldo))
    return out


def fmt_num(v: D, decimal=",", milhares="") -> str:
    s = f"{abs(v):,.2f}"  # 1,234.56
    s = s.replace(",", "§").replace(".", decimal).replace("§", milhares)
    return ("-" if v < 0 else "") + s


def csv_bytes(
    rows, *, sep=";", enc="cp1252", datefmt="%d/%m/%Y", decimal=",", milhares="", header=None, footer=None
):
    out = [sep.join(header or HEADER)]
    for dm, dv, desc, m, s in rows:
        out.append(
            sep.join(
                [
                    dm.strftime(datefmt),
                    dv.strftime(datefmt),
                    desc,
                    fmt_num(m, decimal, milhares),
                    fmt_num(s, decimal, milhares),
                ]
            )
        )
    out += footer or []
    return ("\r\n".join(["Extrato de movimentos", "", *out]) + "\r\n").encode(enc)


def tpl(**kw) -> Template:
    base = {
        "formato": "csv", "codificacao": "cp1252", "separador": ";", "cabecalho": HEADER, "data": "Data", "formato_data": "dd/mm/aaaa",
        "data_valor": "Data valor", "descricao": ["Descrição"], "montante": "Montante", "saldo": "Saldo", "decimal": ",",
    }  # fmt: skip
    return Template(**{**base, **kw})


def tuplo(st):
    return (
        [(m.data_movimento, m.data_valor, m.descricao_original, m.montante, m.saldo_apos, m.ordem_no_dia) for m in st.movimentos],
        st.saldo_inicial, st.saldo_final, st.ordem_ficheiro, bool(st.quebras),
    )  # fmt: skip


def esperado():
    return tuplo(BankinterParser().parse(build_csv()))[0][:], D(SALDO_INICIAL)


def mesmo_que_bankinter(st, ordem="asc"):
    bk = BankinterParser().parse(build_csv())
    assert tuplo(st)[0] == tuplo(bk)[0] and (st.saldo_inicial, st.saldo_final) == (
        bk.saldo_inicial,
        bk.saldo_final,
    )
    assert st.reconciliado and st.ordem_ficheiro == ordem


def parse(t, content):
    return GenericParser(t).parse(content)


# --- estilos aceites ---------------------------------------------------------------------------------------------
def test_csv_ponto_e_virgula_cp1252_datas_com_barra():
    mesmo_que_bankinter(parse(tpl(), csv_bytes(linhas())))


def test_csv_ponto_decimal_com_virgula_de_milhares():
    t = tpl(separador="|", decimal=".", milhares="virgula", formato_data="aaaa-mm-dd")
    c = csv_bytes(linhas(), sep="|", datefmt="%Y-%m-%d", decimal=".", milhares=",")
    assert b"1,000" in c or b"3,407.92" in c  # o ficheiro tem mesmo milhares
    mesmo_que_bankinter(parse(t, c))


def test_csv_utf8_com_espaco_de_milhares_e_datas_com_pontos():
    t = tpl(codificacao="utf-8", formato_data="dd.mm.aaaa", milhares="espaco")
    c = csv_bytes(linhas(), enc="utf-8", datefmt="%d.%m.%Y", milhares=" ")
    mesmo_que_bankinter(parse(t, c))


def test_ficheiro_ordem_decrescente_e_reconhecido():
    st = parse(tpl(), csv_bytes(list(reversed(linhas()))))
    mesmo_que_bankinter(st, "desc")


def test_colunas_de_debito_e_credito():
    h = ["Data", "Descrição", "Débito", "Crédito", "Saldo"]
    rows = ["\r\n".join(["Extrato", ";".join(h)])]
    for dm, _dv, desc, m, s in linhas():
        deb, cred = (fmt_num(-m), "") if m < 0 else ("", fmt_num(m))
        rows.append(";".join([dm.strftime("%d/%m/%Y"), desc, deb, cred, fmt_num(s)]))
    t = tpl(cabecalho=h, data_valor=None, debito="Débito", credito="Crédito", montante=None)
    st = parse(t, ("\r\n".join(rows) + "\r\n").encode("cp1252"))
    assert [m.montante for m in st.movimentos] == [r[3] for r in linhas()] and st.reconciliado


def test_xlsx_com_datas_nativas_e_celulas_numericas():
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Extrato"])
    ws.append(HEADER)
    for dm, dv, desc, m, s in linhas():
        ws.append([dm, dv, desc, float(m), float(s)])
    ws.append([])
    ws.append(["Rodapé legal"])
    buf = io.BytesIO()
    wb.save(buf)
    t = tpl(formato="xlsx", codificacao=None, separador=None, celulas_data_nativas=True)
    mesmo_que_bankinter(parse(t, buf.getvalue()))
    with pytest.raises(
        ParseError, match="data do Excel"
    ):  # modelo de datas em texto não aceita datas nativas
        parse(tpl(formato="xlsx", codificacao=None, separador=None), buf.getvalue())


def test_xls_com_datas_em_texto_e_numeros():
    import xlwt

    wb = xlwt.Workbook()
    ws = wb.add_sheet("x")
    ws.write(0, 0, "Extrato")
    for j, h in enumerate(HEADER):
        ws.write(1, j, h)
    for i, (dm, dv, desc, m, s) in enumerate(linhas(), start=2):
        ws.write(i, 0, dm.strftime("%d/%m/%Y"))
        ws.write(i, 1, dv.strftime("%d/%m/%Y"))
        ws.write(i, 2, desc)
        ws.write(i, 3, float(m))
        ws.write(i, 4, float(s))
    buf = io.BytesIO()
    wb.save(buf)
    mesmo_que_bankinter(parse(tpl(formato="xls", codificacao=None, separador=None), buf.getvalue()))


# --- recusas ------------------------------------------------------------------------------------------------------
def recusa(t, content, texto=None):
    with pytest.raises(ParseError) as e:
        parse(t, content)
    assert "não foi importado" in str(e.value)
    if texto:
        assert texto in str(e.value)


def test_recusa_o_bug_do_ponto_decimal_lido_como_milhares():
    """O caso «-889.50» → -88950: um modelo com decimal «,» não aceita um ficheiro com ponto decimal."""
    recusa(tpl(), csv_bytes(linhas(), decimal="."), "Montante")
    recusa(tpl(decimal=".", milhares="virgula"), csv_bytes(linhas(), decimal=","), "Montante")


def test_recusa_milhares_inconsistentes():
    recusa(tpl(milhares="ponto"), csv_bytes(linhas(), milhares=""), "Saldo")  # 3407,92 sem agrupar


def test_recusa_cabecalho_trocado_ou_renomeado():
    recusa(
        tpl(),
        csv_bytes(linhas(), header=["Data", "Descrição", "Data valor", "Montante", "Saldo"]),
        "Não encontrei",
    )
    recusa(
        tpl(),
        csv_bytes(linhas(), header=["Data", "Data valor", "Descrição", "Valor", "Saldo"]),
        "Não encontrei",
    )
    recusa(tpl(), csv_bytes(linhas(), header=[*HEADER, "Extra"]), "Não encontrei")


def test_recusa_mais_de_2_casas_e_formato_de_data():
    c = csv_bytes(linhas()).replace(b"2,25", b"2,255")
    recusa(tpl(), c, "Montante")
    recusa(tpl(formato_data="dd-mm-aaaa"), csv_bytes(linhas()), "formato inesperado")


def test_recusa_dados_depois_do_fim_e_data_inexistente():
    extra = ["", "Totais", "05/10/2026;05/10/2026;TOTAL;1,00;2,00"]
    recusa(tpl(), csv_bytes(linhas(), footer=extra), "depois")
    c = csv_bytes(linhas()).replace(b"02/10/2026", b"31/02/2026", 1)
    recusa(tpl(), c, "inexistente")


def test_recusa_debito_e_credito_na_mesma_linha():
    h = ["Data", "Descrição", "Débito", "Crédito", "Saldo"]
    c = "\r\n".join(["Extrato", ";".join(h), "01/10/2026;X;1,00;2,00;3,00"]).encode("cp1252")
    recusa(
        tpl(cabecalho=h, data_valor=None, debito="Débito", credito="Crédito", montante=None), c, "mesma linha"
    )


def test_recusa_tipo_de_ficheiro_e_codificacao_erradas():
    recusa(tpl(codificacao="utf-8"), csv_bytes(linhas(), enc="cp1252").replace(b"Descri", b"Descri\xe7"))
    with pytest.raises(ParseError):
        parse(tpl(formato="xls", codificacao=None, separador=None), csv_bytes(linhas()))


# --- modelo -------------------------------------------------------------------------------------------------------
def test_modelo_so_aceita_valores_fixos_e_coerentes():
    ok = tpl().model_dump()
    for mudanca in (
        {"formato_data": "%d/%m/%Y"},  # nada de strptime vindo do cliente
        {"extra": 1},
        {"saldo": "Inexistente"},
        {"decimal": ".", "milhares": "ponto"},
        {"montante": None},
        {"descricao": ["Saldo"]},  # a mesma coluna com dois papéis
        {"codificacao": None},
    ):
        with pytest.raises(ValidationError):
            Template(**{**ok, **mudanca})


# --- ponta a ponta pela API ---------------------------------------------------------------------------------------
def test_conta_generica_importa_e_recusa_pela_api(api, db):
    t = tpl().model_dump(mode="json")
    c = api.post(
        "/api/accounts",
        json={"nome": "Outro", "banco": "Banco X", "parser_id": "generico", "config_importacao": t},
    )
    assert c.status_code == 201, c.text
    cid = c.json()["id"]
    r = api.post(
        "/api/imports/preview",
        data={"conta_id": cid},
        files={"file": ("x.csv", csv_bytes(linhas()), "text/csv")},
    )
    assert r.status_code == 200 and r.json()["reconciliado"] and len(r.json()["linhas"]) == len(ROWS)
    bad = api.post(
        "/api/imports/preview",
        data={"conta_id": cid},
        files={"file": ("y.csv", csv_bytes(linhas(), decimal="."), "text/csv")},
    )
    assert bad.status_code == 422 and "não foi importado" in str(bad.json())
    # modelo inválido ou em falta
    assert (
        api.post(
            "/api/accounts",
            json={"nome": "Z", "banco": "B", "parser_id": "generico", "config_importacao": {"x": 1}},
        ).status_code
        == 422
    )
    assert (
        api.post(
            "/api/accounts",
            json={"nome": "Z", "banco": "B", "parser_id": "bankinter", "config_importacao": t},
        ).status_code
        == 422
    )
    vazia = api.post("/api/accounts", json={"nome": "W", "banco": "B", "parser_id": "pendente"}).json()["id"]
    assert (
        api.patch(
            f"/api/accounts/{vazia}", json={"parser_id": "generico", "config_importacao": {}}
        ).status_code
        == 422
    )
