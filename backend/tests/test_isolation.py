"""Isolamento por dono: cada utilizador só vê e altera o que é seu (contas, regras, categorias, movimentos...).

`A` é o utilizador da fixture `api`; `B` é um segundo utilizador com o seu próprio cliente (cookies separados).
"""

from pathlib import Path

from fastapi.testclient import TestClient

from app.cli import create_user
from app.main import app

from .conftest import ROWS, build_csv
from .test_categorization_api import cat_id, import_all, mk_rule, txs
from .test_imports import confirm

PW = "outra-password-longa"


def make_user(db, username="maria"):
    """Utilizador B autenticado, com uma conta própria; devolve (cliente, conta_id)."""
    create_user(username, username.title(), PW)
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": username, "password": PW})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    conta = c.post(
        "/api/accounts", json={"nome": "Ordenado", "banco": "Bankinter", "parser_id": "bankinter_csv"}
    )
    assert conta.status_code == 201, conta.text  # o mesmo nome que a conta do A: únicos por dono
    return c, conta.json()["id"]


def import_into(c, conta_id, rows=None):
    r = c.post(
        "/api/imports/preview",
        data={"conta_id": conta_id},
        files={"file": ("x.csv", build_csv(rows), "text/csv")},
    )
    assert r.status_code == 200, r.text
    return confirm(c, r.json()["id"])


def my_cat(c, nome):
    return next(x["id"] for x in c.get("/api/categories").json() if x["nome"] == nome)


def test_regras_e_categorizacoes_de_A_nao_chegam_ao_importar_de_B(api, db):
    """O teste que apanha fugas nos serviços: regras e histórico de A não categorizam as linhas de B."""
    sup_a = cat_id(db, "Supermercado")
    mk_rule(api, padrao="SUPERMERCADO", categoria_id=sup_a)
    import_all(api)
    tid = txs(api, q="LOJA A")["items"][0]["id"]
    api.patch(f"/api/transactions/{tid}", json={"categoria_id": cat_id(db, "Online")})  # manual de A
    antes = api.get("/api/analytics/by-category").json()

    b, conta_b = make_user(db)
    import_into(b, conta_b)
    itens = b.get("/api/transactions").json()["items"]
    assert len(itens) == len(ROWS)
    assert all(m["categoria_id"] is None for m in itens)  # nada de A foi aplicado
    assert b.get("/api/rules/search").json()["total"] == 0
    assert api.get("/api/analytics/by-category").json() == antes  # os totais de A não mudaram
    assert api.get("/api/transactions").json()["total"] == len(ROWS)  # e A só vê as suas linhas


def test_B_nao_ve_nada_de_A(api, db):
    mk_rule(api, padrao="SUPERMERCADO", categoria_id=cat_id(db, "Supermercado"))
    import_all(api)
    b = make_user(db)[0]
    assert b.get("/api/transactions").json()["total"] == 0
    assert b.get("/api/transactions/uncategorized").json()["total"] == 0
    assert b.get("/api/transactions/uncategorized", params={"group_by": "description"}).json()["grupos"] == []
    assert [a["id"] for a in b.get("/api/accounts").json()] != [api.conta_id]
    assert b.get("/api/rules").json() == []
    assert b.get("/api/imports").json() == []
    assert [u["username"] for u in b.get("/api/users").json()] == ["maria"]
    assert b.get("/api/coverage").json()[0]["n_movimentos"] == 0
    s = b.get("/api/analytics/summary").json()
    assert (s["despesas"], s["receitas"], s["n_por_categorizar"]) == ("0.00", "0.00", 0)
    assert b.get("/api/analytics/by-category").json()["itens"] == []
    assert b.get("/api/analytics/monthly").json()["periodos"][-1]["despesas"] == "0.00"
    assert b.get("/api/analytics/category-matrix").json()["linhas"] == []
    assert b.get("/api/analytics/kpis").json()["reserva_meses"] is None
    ids_a = {c["id"] for c in api.get("/api/categories").json()}
    assert not ids_a & {c["id"] for c in b.get("/api/categories").json()}  # categorias próprias


def test_B_com_ids_de_A_recebe_404(api, db):
    sup = cat_id(db, "Supermercado")
    rule = mk_rule(api, padrao="SUPERMERCADO", categoria_id=sup)["id"]
    imp = import_all(api)["id"]
    tid = txs(api)["items"][0]["id"]
    b = make_user(db)[0]
    sup_b = my_cat(b, "Supermercado")
    antes = txs(api)["items"]
    assert b.patch(f"/api/accounts/{api.conta_id}", json={"nome": "x"}).status_code == 404
    assert b.patch(f"/api/transactions/{tid}", json={"notas": "x"}).status_code == 404
    assert b.patch(f"/api/rules/{rule}", json={"ativa": False}).status_code == 404
    assert b.delete(f"/api/rules/{rule}").status_code == 404
    assert b.post(f"/api/rules/{rule}/preview-impact").status_code == 404
    assert b.patch(f"/api/categories/{sup}", json={"nome": "x"}).status_code == 404
    assert b.delete(f"/api/categories/{sup}").status_code == 404
    assert b.get(f"/api/imports/{imp}").status_code == 404
    assert b.post(f"/api/imports/{imp}/confirm", json={}).status_code == 404
    assert b.delete(f"/api/imports/{imp}").status_code == 404
    r = b.post(
        "/api/imports/preview",
        data={"conta_id": api.conta_id},
        files={"file": ("x.csv", build_csv(), "text/csv")},
    )
    assert r.status_code == 404
    # referências a objetos de A dentro de corpos de pedidos
    assert b.post("/api/rules", json={"padrao": "XPTO", "categoria_id": sup}).status_code == 422
    assert (
        b.post(
            "/api/rules", json={"padrao": "XPTO", "categoria_id": sup_b, "conta_id": api.conta_id}
        ).status_code
        == 422
    )
    assert b.post("/api/categories", json={"nome": "Filha", "parent_id": sup}).status_code == 422
    bulk = b.post("/api/transactions/bulk-categorize", json={"ids": [tid], "categoria_id": sup_b})
    assert bulk.status_code == 404
    por_desc = b.post(
        "/api/transactions/bulk-categorize",
        json={"descricao_normalizada": antes[0]["descricao_normalizada"], "categoria_id": sup_b},
    )
    assert por_desc.status_code == 404  # a descrição de A não apanha linhas de A
    restore = b.post(
        "/api/transactions/restore",
        json={
            "itens": [{"id": tid, "categoria_id": sup_b, "categoria_origem": "manual"}],
            "apagar_regra_id": rule,
        },
    )
    assert restore.json() == {"restaurados": 0, "regra_apagada": False}
    assert b.post("/api/rules/apply").json()["movimentos_alterados"] == 0
    assert txs(api)["items"] == antes  # nada de A mudou
    assert api.get("/api/rules").json() != []  # a regra de A continua lá


def test_a_mesma_conta_e_categoria_em_utilizadores_diferentes_nao_colide(api, db):
    b, conta_b = make_user(db)
    assert b.post("/api/categories", json={"nome": "Minha", "tipo": "despesa"}).status_code == 201
    assert api.post("/api/categories", json={"nome": "Minha", "tipo": "despesa"}).status_code == 201
    assert conta_b != api.conta_id


def test_sessoes_independentes(api, db):
    b = make_user(db)[0]
    b.post("/api/auth/logout")
    assert b.get("/api/auth/me").status_code == 401
    assert api.get("/api/auth/me").status_code == 200


def test_routers_nao_ignoram_o_utilizador_autenticado():
    """Regra de projeto: um router que usa `_: Auth` não sabe quem é o utilizador, logo não pode isolar por dono."""
    routers = Path(__file__).resolve().parents[1] / "app" / "api" / "routers"
    permitidos = {"health.py", "auth.py", "__init__.py"}
    ofensores = [
        f.name for f in routers.glob("*.py") if f.name not in permitidos and "_: Auth" in f.read_text()
    ]
    assert not ofensores, f"use `auth: Auth` e limite por dono (api/scope.py): {ofensores}"
