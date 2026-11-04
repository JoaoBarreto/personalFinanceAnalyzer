"""O anonimizador de extratos (scripts/mask_statement.py) não pode deixar passar descrições nem valores."""

import importlib.util
from pathlib import Path

import pytest

from .conftest import ROWS, build_csv, build_xls

_spec = importlib.util.spec_from_file_location(
    "mask_statement", Path(__file__).resolve().parents[2] / "scripts" / "mask_statement.py"
)
ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ms)  # o script (linha de comandos) usa o serviço da app


def _run(tmp_path, capsys, content: bytes, name: str, **kw) -> str:
    p = tmp_path / name
    p.write_bytes(content)
    ms.describe(str(p), kw.get("show_all", False))
    return capsys.readouterr().out


@pytest.mark.parametrize("kind", ["xls", "csv"])
def test_saida_nao_contem_descricoes_nem_valores(tmp_path, capsys, kind):
    content = build_xls() if kind == "xls" else build_csv()
    out = _run(tmp_path, capsys, content, f"extrato.{kind}")
    for _d1, _d2, desc, montante in ROWS:
        for palavra in desc.split():
            if len(palavra) > 3 and palavra.isalpha():
                assert palavra not in out, palavra
        for raw in (str(montante).replace("-", ""), str(montante).replace("-", "").replace(".", ",")):
            assert raw not in out, raw
    assert "linha do cabeçalho" in out


def test_formatos_de_data_e_numero_ficam_visiveis(tmp_path, capsys):
    out = _run(tmp_path, capsys, build_csv(), "extrato.csv")
    assert "99-99-9999" in out  # forma das datas
    assert "9,99" in out  # vírgula decimal com 2 casas


def test_vocabulario_generico_aparece_sem_mascara_e_o_resto_nao(tmp_path, capsys):
    out = _run(tmp_path, capsys, build_csv(), "extrato.csv")
    assert "Montante" in out and "Saldo" in out
    assert "EMPRESA" not in out and "SUPERMERCADO" not in out


def test_pdf_nao_suportado(tmp_path):
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF-1.7 ...")
    with pytest.raises(SystemExit):
        ms.describe(str(p), False)


def test_endpoint_estrutura_mascara_e_nao_grava_nada(api, db):
    r = api.post("/api/banks/structure", files={"file": ("x.csv", build_csv(), "text/csv")})
    assert r.status_code == 200
    out = r.json()["estrutura"]
    for _d1, _d2, desc, _m in ROWS:
        for palavra in desc.split():
            if len(palavra) > 3 and palavra.isalpha():
                assert palavra not in out, palavra
    assert "99-99-9999" in out and "Montante" in out
    assert api.get("/api/imports").json() == []  # nada foi gravado


def test_endpoint_estrutura_recusa_pdf_e_lixo(api, db):
    assert (
        api.post(
            "/api/banks/structure", files={"file": ("x.pdf", b"%PDF-1.7 x", "application/pdf")}
        ).status_code
        == 415
    )
    lixo = api.post(
        "/api/banks/structure",
        files={"file": ("x.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 lixo", "application/vnd.ms-excel")},
    )
    assert lixo.status_code == 422 and "lixo" not in lixo.text


def test_lista_de_bancos_e_conta_pendente(api, db):
    bancos = api.get("/api/banks").json()
    assert [b["parser_id"] for b in bancos] == ["bankinter"]
    c = api.post("/api/accounts", json={"nome": "Outro", "banco": "Banco X", "parser_id": "pendente"})
    assert c.status_code == 201
    r = api.post(
        "/api/imports/preview",
        data={"conta_id": c.json()["id"]},
        files={"file": ("x.csv", build_csv(), "text/csv")},
    )
    assert r.status_code == 422 and "ainda não está suportado" in r.json()["detail"]
    assert api.get("/api/imports").json() == []  # não ficou registo de erro
    assert (
        api.patch(f"/api/accounts/{c.json()['id']}", json={"parser_id": "bankinter"}).json()["parser_id"]
        == "bankinter"
    )
    assert api.patch(f"/api/accounts/{c.json()['id']}", json={"parser_id": "inexistente"}).status_code == 422
