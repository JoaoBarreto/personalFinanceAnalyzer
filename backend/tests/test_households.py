"""Dois utilizadores, dados partilhados, contas com titular (PRD 3.1 e 3.1.1)."""

from fastapi.testclient import TestClient

from app.cli import create_user
from app.main import app

from .conftest import ROWS, build_csv
from .test_categorization_api import cat_id, import_all, txs
from .test_imports import confirm


def login(username, pw="outra-password-longa"):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": username, "password": pw})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return c


def upload(c, conta_id, rows):
    r = c.post(
        "/api/imports/preview",
        data={"conta_id": conta_id},
        files={"file": ("x.csv", build_csv(rows), "text/csv")},
    )
    assert r.status_code == 200, r.text
    return confirm(c, r.json()["id"])


def mk_account(c, nome, titular_id=None):
    r = c.post(
        "/api/accounts",
        json={"nome": nome, "banco": "Bankinter", "parser_id": "bankinter_csv", "titular_id": titular_id},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_dois_utilizadores_veem_os_mesmos_dados(api, db):
    create_user("maria", "Maria", "outra-password-longa")
    import_all(api)
    maria = login("maria")
    assert maria.get("/api/transactions").json()["total"] == len(ROWS)
    assert [u["username"] for u in maria.get("/api/users").json()] == ["joao", "maria"]
    assert "password_hash" not in maria.get("/api/users").text


def test_regista_quem_categorizou(api, db):
    create_user("maria", "Maria", "outra-password-longa")
    import_all(api)
    maria = login("maria")
    tid = txs(api, q="SUPERMERCADO")["items"][0]["id"]
    r = maria.patch(f"/api/transactions/{tid}", json={"categoria_id": cat_id(db, "Supermercado")})
    maria_id = next(u["id"] for u in api.get("/api/users").json() if u["username"] == "maria")
    assert r.json()["atualizado_por"] == maria_id
    assert txs(api, q="EMPRESA")["items"][0]["atualizado_por"] != maria_id  # importado por João


def test_sessoes_independentes(api, db):
    create_user("maria", "Maria", "outra-password-longa")
    maria = login("maria")
    maria.post("/api/auth/logout")
    assert maria.get("/api/auth/me").status_code == 401
    assert api.get("/api/auth/me").status_code == 200  # a sessão do João não foi afetada


def test_filtro_por_titular(api, db):
    create_user("maria", "Maria", "outra-password-longa")
    users = {u["username"]: u["id"] for u in api.get("/api/users").json()}
    minha = api.conta_id
    api.patch(f"/api/accounts/{minha}", json={"titular_id": users["joao"]})
    dela = mk_account(api, "Dela", users["maria"])["id"]
    conjunta = mk_account(api, "Casal")["id"]
    upload(api, minha, ROWS)  # 8 movimentos
    upload(api, dela, ROWS[:3])
    upload(api, conjunta, ROWS[:1])

    def total(**p):
        return api.get("/api/transactions", params=p).json()["total"]

    assert total() == 8 + 3 + 1
    assert total(titular=users["joao"]) == 8
    assert total(titular=users["maria"]) == 3
    assert total(titular="conjunta") == 1
    assert total(titular=users["maria"], conta_id=minha) == 0  # filtros combinam-se (E)

    def desp(**p):
        return api.get(
            "/api/analytics/summary", params={"data_de": "2026-10-01", "data_ate": "2026-10-31", **p}
        ).json()

    assert desp(titular=users["joao"])["despesas"] == "872.99"
    assert desp(titular=users["maria"])["despesas"] == "670.39"  # 2,25 + 668,14 (3 primeiras linhas)
    assert desp(titular="conjunta")["despesas"] == "0.00"
    assert api.get("/api/analytics/by-category", params={"titular": "conjunta"}).json()["itens"] == []
    assert api.get("/api/analytics/monthly", params={"titular": users["maria"]}).status_code == 200
    assert api.get("/api/transactions", params={"titular": "xpto"}).status_code == 422


def test_contas_titular_validado(api, db):
    r = api.post(
        "/api/accounts",
        json={"nome": "X", "banco": "B", "parser_id": "bankinter_csv", "titular_id": 999999},
    )
    assert r.status_code == 422
    assert api.patch(f"/api/accounts/{api.conta_id}", json={"titular_id": 999999}).status_code == 422
    assert api.patch("/api/accounts/999999", json={"nome": "Y"}).status_code == 404
    api.patch(f"/api/accounts/{api.conta_id}", json={"arquivada": True})
    up = api.post(
        "/api/imports/preview",
        data={"conta_id": api.conta_id},
        files={"file": ("x.csv", build_csv(), "text/csv")},
    )
    assert up.status_code == 404  # conta arquivada não aceita importações
