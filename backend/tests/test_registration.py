"""Registo de utilizadores pela web: primeiro utilizador, limites, isolamento e login sem distinção de maiúsculas."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import config, rate_limit
from app.cli import create_user
from app.main import app
from app.models import Categoria, Utilizador

from .test_categorization_api import import_all

PW = "uma-password-longa"


def novo_cliente() -> TestClient:
    return TestClient(app)


def registar(c, username="ana", nome="Ana", password=PW):
    return c.post("/api/auth/register", json={"username": username, "nome": nome, "password": password})


@pytest.fixture
def vazio(db):
    """Base sem utilizadores (a fixture `db` já os apaga)."""
    rate_limit.reset()
    with novo_cliente() as c:
        yield c


def test_config_publica_sem_utilizadores_e_com_utilizadores(vazio, db, monkeypatch):
    assert vazio.get("/api/auth/config").json() == {"registo_aberto": True, "sem_utilizadores": True}
    create_user("joao", "João", PW)
    assert vazio.get("/api/auth/config").json() == {"registo_aberto": True, "sem_utilizadores": False}
    monkeypatch.setattr(config, "ALLOW_REGISTRATION", False)
    assert vazio.get("/api/auth/config").json() == {"registo_aberto": False, "sem_utilizadores": False}


def test_registo_inicia_sessao_e_cria_as_categorias_do_utilizador(vazio, db):
    r = registar(vazio, "Ana", " Ana Silva ")
    assert r.status_code == 201 and r.json()["username"] == "ana" and r.json()["nome"] == "Ana Silva"
    vazio.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    assert vazio.get("/api/auth/me").json()["username"] == "ana"  # sessão iniciada
    cats = vazio.get("/api/categories").json()
    assert len(cats) > 30 and "Poupança/Investimento" in {c["nome"] for c in cats}
    assert vazio.get("/api/auth/config").json()["sem_utilizadores"] is False
    # e já pode criar uma conta e usar a app
    assert (
        vazio.post(
            "/api/accounts", json={"nome": "Ordenado", "banco": "Bankinter", "parser_id": "bankinter"}
        ).status_code
        == 201
    )


def test_primeiro_utilizador_pode_registar_mesmo_com_o_registo_desligado(vazio, db, monkeypatch):
    monkeypatch.setattr(config, "ALLOW_REGISTRATION", False)
    assert registar(vazio).status_code == 201
    with novo_cliente() as outro:
        r = registar(outro, "bia", "Bia")
        assert r.status_code == 403 and "desativado" in r.json()["detail"]
    assert db.scalar(select(func.count()).select_from(Utilizador)) == 1


def test_registo_ligado_deixa_registar_mais_utilizadores(vazio, db):
    assert registar(vazio).status_code == 201
    with novo_cliente() as outro:
        assert registar(outro, "bia", "Bia").status_code == 201


def test_recusa_nome_repetido_com_outras_maiusculas_e_dados_invalidos(vazio, db):
    assert registar(vazio, "ana").status_code == 201
    with novo_cliente() as c:
        assert registar(c, "ANA").status_code == 409
        assert registar(c, " Ana ").status_code == 409
        assert registar(c, "a").status_code == 422  # curto
        assert registar(c, "ana silva").status_code == 422  # espaço
        assert registar(c, "ana/../x").status_code == 422
        assert registar(c, "bia", password="curta").status_code == 422
        assert registar(c, "bia", password="x" * 600).status_code == 422
        assert registar(c, "bia", nome="").status_code == 422
        assert registar(c, "bia", nome="n" * 500).status_code == 422
    assert db.scalar(select(func.count()).select_from(Utilizador)) == 1


def test_limite_de_registos_por_ip(vazio, db, monkeypatch):
    monkeypatch.setattr(config, "REGISTER_MAX", 3)
    codigos = [registar(vazio, f"user{i}", f"U{i}").status_code for i in range(5)]
    assert codigos == [201, 201, 201, 429, 429]


def test_login_nao_distingue_maiusculas_e_continua_a_recusar_passwords_erradas(vazio, db):
    registar(vazio, "ana")
    with novo_cliente() as c:
        assert c.post("/api/auth/login", json={"username": "ANA", "password": PW}).status_code == 200
    with novo_cliente() as c:
        assert (
            c.post("/api/auth/login", json={"username": "ana", "password": "errada-errada"}).status_code
            == 401
        )
    create_user("Maria", "Maria", PW)  # a CLI normaliza igual
    assert db.scalar(select(Utilizador.username).where(Utilizador.nome == "Maria")) == "maria"


def test_utilizador_registado_nao_ve_dados_de_outro(api, db):
    import_all(api)  # dados do utilizador «joao» (fixture api)
    with novo_cliente() as c:
        r = registar(c, "ana", "Ana")
        c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
        assert c.get("/api/transactions").json()["total"] == 0
        assert c.get("/api/accounts").json() == []
        assert c.get("/api/users").json()[0]["username"] == "ana"
        mine = {x["id"] for x in c.get("/api/categories").json()}
        assert not mine & {x["id"] for x in api.get("/api/categories").json()}
    assert db.scalar(select(func.count()).select_from(Categoria).where(Categoria.dono_id.is_not(None))) > 60
