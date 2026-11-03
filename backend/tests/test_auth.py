from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from app.cli import create_user
from app.models import Sessao
from app.security import hash_token

PW = "uma-password-longa"


@pytest.fixture
def user(db):
    create_user("joao", "João", PW)


def login(client, pw=PW):
    return client.post("/api/auth/login", json={"username": "joao", "password": pw})


def test_health_aberto(client):
    assert client.get("/api/health").status_code == 200


def test_sem_sessao_401(client):
    assert client.get("/api/auth/me").status_code == 401


def test_login_ok_define_cookie_e_csrf(client, user):
    r = login(client)
    assert r.status_code == 200
    set_cookie = r.headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "samesite=lax" in set_cookie
    assert r.json()["username"] == "joao" and r.json()["csrf_token"]
    me = client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["nome"] == "João"


def test_token_nunca_guardado_em_claro(client, user, db):
    login(client)
    token = client.cookies.get("session")
    hashes = db.scalars(select(Sessao.token_hash)).all()
    assert hashes == [hash_token(token)] and token not in hashes


def test_password_errada_e_utilizador_inexistente(client, user):
    assert login(client, "errada-errada").status_code == 401
    r = client.post("/api/auth/login", json={"username": "ninguem", "password": PW})
    assert r.status_code == 401 and r.json() == login(client, "errada-errada").json()


def test_rate_limit(client, user):
    for _ in range(5):
        assert login(client, "errada-errada").status_code == 401
    assert login(client, "errada-errada").status_code == 429
    assert login(client).status_code == 429  # mesmo com a password certa, enquanto bloqueado


def test_logout_exige_csrf_e_invalida_sessao(client, user):
    csrf = login(client).json()["csrf_token"]
    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": "errado"}).status_code == 403
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_sessao_expirada(client, user, db):
    login(client)
    db.execute(text("UPDATE sessoes SET expira_em = :t"), {"t": datetime.now(UTC) - timedelta(seconds=1)})
    db.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_utilizador_desativado(client, user, db):
    login(client)
    db.execute(text("UPDATE utilizadores SET ativo = false"))
    db.commit()
    assert client.get("/api/auth/me").status_code == 401
    assert login(client).status_code == 401


def test_password_curta_recusada(db):
    with pytest.raises(SystemExit):
        create_user("x", "X", "curta")
