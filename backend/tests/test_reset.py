from decimal import Decimal as D

from sqlalchemy import func, select

from app.cli import reset_movements
from app.models import Categoria, Conta, Importacao, Movimento, Regra, Utilizador
from app.services import reset

from .conftest import ROWS, build_csv
from .test_categorization_api import cat_id, import_all, txs
from .test_imports import confirm, up


def test_reset_apaga_dados_e_mantem_o_trabalho_de_categorizacao(api, db):
    import_all(api)
    sup, alim = cat_id(db, "Supermercado"), cat_id(db, "Restaurantes")
    manual = next(t for t in txs(api)["items"] if t["descricao_normalizada"] == "SUPERMERCADO")
    api.patch(f"/api/transactions/{manual['id']}", json={"categoria_id": sup})  # à mão, sem regra
    api.post("/api/rules", json={"padrao": "EMPRESA", "categoria_id": alim})  # uma regra já existente
    api.post("/api/rules/apply")
    n_cats = db.scalar(select(func.count()).select_from(Categoria))
    assert reset.preview(db)["categorizacoes_manuais"] == 1

    r = reset.reset_movements(db)
    assert r == {"movimentos_apagados": len(ROWS), "importacoes_apagadas": 1, "regras_criadas": 1}
    assert db.scalar(select(func.count()).select_from(Movimento)) == 0
    assert db.scalar(select(func.count()).select_from(Importacao)) == 0
    # o que NÃO se apaga
    assert db.scalar(select(func.count()).select_from(Categoria)) == n_cats
    assert (
        db.scalar(select(func.count()).select_from(Conta)) == 1
        and db.scalar(select(func.count()).select_from(Utilizador)) >= 1
    )
    regras = {(x.padrao, x.tipo_match, x.origem) for x in db.scalars(select(Regra))}
    assert ("SUPERMERCADO", "igual", "aprendida") in regras and ("EMPRESA", "contem", "manual") in regras
    assert all(x.n_aplicacoes == 0 for x in db.scalars(select(Regra)))

    # reimportar: as categorizações voltam sozinhas (agora por regra) e o mesmo ficheiro pode ser carregado
    confirm(api, up(api, build_csv()).json()["id"])
    por_desc = {t["descricao_normalizada"]: t for t in txs(api)["items"]}
    assert (
        por_desc["SUPERMERCADO"]["categoria_id"] == sup
        and por_desc["SUPERMERCADO"]["categoria_origem"] == "regra"
    )
    assert por_desc["EMPRESA X"]["categoria_id"] == alim


def test_reset_converte_a_categoria_mais_frequente_e_nao_duplica_regras(api, db):
    rows = [
        ("03-01-2026", "03-01-2026", "COMPRA 0000000.01 CONTINENTE", D("-10.00")),
        ("04-01-2026", "04-01-2026", "COMPRA 0000000.02 CONTINENTE", D("-11.00")),
        ("05-01-2026", "05-01-2026", "COMPRA 0000000.03 CONTINENTE", D("-12.00")),
    ]
    import_all(api, rows)
    sup, alim = cat_id(db, "Supermercado"), cat_id(db, "Restaurantes")
    ids = [t["id"] for t in txs(api)["items"]]
    for i, c in zip(ids, (sup, sup, alim), strict=True):  # 2 × Supermercado, 1 × Restaurantes
        api.patch(f"/api/transactions/{i}", json={"categoria_id": c})
    assert reset.reset_movements(db)["regras_criadas"] == 1
    assert [(x.padrao, x.categoria_id) for x in db.scalars(select(Regra))] == [("CONTINENTE", sup)]
    assert reset.reset_movements(db) == {
        "movimentos_apagados": 0,
        "importacoes_apagadas": 0,
        "regras_criadas": 0,
    }


def test_cli_pede_confirmacao_e_pode_ser_cancelada(api, db, monkeypatch):
    import pytest

    import_all(api)
    monkeypatch.setattr("builtins.input", lambda _="": "nao")
    with pytest.raises(SystemExit, match="Cancelado"):
        reset_movements(yes=False)
    assert db.scalar(select(func.count()).select_from(Movimento)) == len(ROWS)  # nada foi apagado
    monkeypatch.setattr("builtins.input", lambda _="": "APAGAR")
    reset_movements(yes=False)
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Movimento)) == 0


def test_reset_apaga_tambem_previews_e_importacoes_revertidas(api, db):
    p = up(api, build_csv()).json()  # fica em preview
    other = confirm(api, up(api, build_csv(ROWS[:3])).json()["id"]).json()["id"]
    api.delete(f"/api/imports/{other}")  # revertida
    r = reset.reset_movements(db)
    assert r["importacoes_apagadas"] == 2 and p["id"]
