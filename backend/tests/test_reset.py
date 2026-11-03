from decimal import Decimal as D

import pytest
from sqlalchemy import func, select

from app.cli import reset_movements
from app.models import Categoria, CategorizacaoGuardada, Conta, Importacao, Movimento, Regra, Utilizador
from app.services import reset

from .conftest import ROWS, build_csv
from .test_categorization_api import cat_id, import_all, txs
from .test_imports import confirm, up

N = lambda db, model: db.scalar(select(func.count()).select_from(model))


def _por_linha(api):
    """{(data, descrição, montante): (categoria, origem)} de todos os movimentos."""
    return {
        (t["data_movimento"], t["descricao_normalizada"], t["montante"]): (
            t["categoria_nome"],
            t["categoria_origem"],
        )
        for t in api.get("/api/transactions", params={"page_size": 200}).json()["items"]
    }


def _extrato_com_excecoes():
    """A mesma descrição em linhas diferentes (dias diferentes e duas no mesmo dia), para categorias diferentes."""
    d = "TRF A CREDITO SEPA+ - PESSOA X"
    return [
        ("03-01-2026", "03-01-2026", d, D("-50.00")),
        ("10-02-2026", "10-02-2026", d, D("-60.00")),
        ("10-02-2026", "10-02-2026", d, D("-70.00")),  # mesmo dia e mesma descrição, categoria diferente
        ("15-03-2026", "15-03-2026", "COMPRA 0000000.01 SUPERMERCADO Y", D("-20.00")),
        ("20-04-2026", "20-04-2026", "COMPRA 0000000.02 LOJA SEM REGRA", D("-9.99")),
    ]


def test_reset_guarda_cada_escolha_manual_e_reaplica_exatamente(api, db):
    rows = _extrato_com_excecoes()
    import_all(api, rows)
    ids = {(t["data_movimento"], t["montante"]): t["id"] for t in txs(api)["items"]}
    sup, alim, viag = cat_id(db, "Supermercado"), cat_id(db, "Restaurantes"), cat_id(db, "Viagens")
    for k, c in (
        (("2026-01-03", "-50.00"), sup),
        (("2026-02-10", "-60.00"), alim),
        (("2026-02-10", "-70.00"), viag),
    ):
        api.patch(
            f"/api/transactions/{ids[k]}", json={"categoria_id": c}
        )  # exceções: 3 categorias, mesma descrição
    api.post("/api/rules", json={"padrao": "SUPERMERCADO", "categoria_id": sup})
    api.post("/api/rules/apply")  # esta linha fica categorizada POR REGRA (não é manual)
    antes = _por_linha(api)
    n_cats, n_regras = N(db, Categoria), N(db, Regra)
    assert reset.preview(db) == {
        "movimentos": 5,
        "importacoes": 1,
        "categorizacoes_manuais": 3,
        "descricoes_com_excecoes": 1,
    }

    r = reset.reset_movements(db)
    assert (
        r["movimentos_apagados"] == 5
        and r["importacoes_apagadas"] == 1
        and r["categorizacoes_guardadas"] == 3
    )
    assert N(db, Movimento) == 0 and N(db, Importacao) == 0 and N(db, CategorizacaoGuardada) == 3
    assert (N(db, Categoria), N(db, Regra), N(db, Conta)) == (n_cats, n_regras, 1) and N(db, Utilizador) >= 1
    assert all(x.n_aplicacoes == 0 for x in db.scalars(select(Regra)))

    # reimportar o MESMO extrato: tudo volta exatamente como estava, incluindo as exceções
    p = up(api, build_csv(rows)).json()
    assert confirm(api, p["id"]).json()["categorizacoes_restauradas"] == 3
    assert _por_linha(api) == antes
    assert N(db, CategorizacaoGuardada) == 0  # consumidas: não ficam a pairar


def test_so_se_reaplica_a_linhas_que_coincidem_em_conta_data_e_descricao(api, db):
    rows = _extrato_com_excecoes()
    import_all(api, rows)
    sup = cat_id(db, "Supermercado")
    for t in txs(api)["items"]:
        api.patch(f"/api/transactions/{t['id']}", json={"categoria_id": sup})
    reset.reset_movements(db)
    assert N(db, CategorizacaoGuardada) == 5
    # um extrato parcial (só 2 das linhas) + uma linha com a mesma descrição mas OUTRA data
    parcial = [rows[0], rows[3], ("07-07-2026", "07-07-2026", rows[0][2], D("-1.00"))]
    r = confirm(api, up(api, build_csv(parcial)).json()["id"]).json()
    assert r["categorizacoes_restauradas"] == 2
    por = {t["data_movimento"]: t for t in txs(api)["items"]}
    assert (
        por["2026-01-03"]["categoria_origem"] == "manual"
        and por["2026-03-15"]["categoria_origem"] == "manual"
    )
    # outra data: não consome nenhuma guardada (não é «manual»); só o histórico da mesma descrição a categoriza
    assert por["2026-07-07"]["categoria_origem"] == "historico"
    assert N(db, CategorizacaoGuardada) == 3  # as 3 que não coincidiram continuam guardadas


def test_reverter_uma_importacao_nao_perde_as_escolhas_manuais(api, db):
    p = up(api, build_csv()).json()
    confirm(api, p["id"])
    sup = cat_id(db, "Supermercado")
    tid = next(t["id"] for t in txs(api)["items"] if t["descricao_normalizada"] == "SUPERMERCADO")
    api.patch(f"/api/transactions/{tid}", json={"categoria_id": sup})
    assert api.delete(f"/api/imports/{p['id']}").status_code == 204
    assert N(db, Movimento) == 0 and N(db, CategorizacaoGuardada) == 1
    again = confirm(api, up(api, build_csv()).json()["id"]).json()
    assert again["categorizacoes_restauradas"] == 1
    t = next(t for t in txs(api)["items"] if t["descricao_normalizada"] == "SUPERMERCADO")
    assert t["categoria_id"] == sup and t["categoria_origem"] == "manual"


def test_cli_mostra_o_que_vai_acontecer_e_pode_ser_cancelada(api, db, monkeypatch, capsys):
    rows = _extrato_com_excecoes()
    import_all(api, rows)
    sup, alim = cat_id(db, "Supermercado"), cat_id(db, "Restaurantes")
    for t, c in zip(txs(api)["items"][:2], (sup, alim), strict=True):
        api.patch(f"/api/transactions/{t['id']}", json={"categoria_id": c})
    monkeypatch.setattr("builtins.input", lambda _="": "nao")
    with pytest.raises(SystemExit, match="Cancelado"):
        reset_movements(yes=False)
    err = capsys.readouterr().err
    assert (
        "Vai apagar 5 movimentos" in err
        and "2 categorizações feitas à mão ficam guardadas linha a linha" in err
    )
    assert N(db, Movimento) == 5  # nada foi apagado
    monkeypatch.setattr("builtins.input", lambda _="": "APAGAR")
    reset_movements(yes=False)
    db.expire_all()
    assert N(db, Movimento) == 0 and N(db, CategorizacaoGuardada) == 2


def test_reset_apaga_tambem_previews_e_importacoes_revertidas(api, db):
    up(api, build_csv())  # fica em preview
    other = confirm(api, up(api, build_csv(ROWS[:3])).json()["id"]).json()["id"]
    api.delete(f"/api/imports/{other}")  # revertida
    assert reset.reset_movements(db)["importacoes_apagadas"] == 2


def test_reset_repetido_nao_faz_nada(api, db):
    import_all(api)
    reset.reset_movements(db)
    r = reset.reset_movements(db)
    assert (
        r["movimentos_apagados"] == 0
        and r["importacoes_apagadas"] == 0
        and r["categorizacoes_guardadas"] == 0
    )
