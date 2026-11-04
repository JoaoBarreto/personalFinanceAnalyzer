"""PRD §9: sem autenticação não há acesso a nenhum endpoint, exceto /api/health, /api/auth/login, /api/auth/register e /api/auth/config.

Cobre automaticamente todas as rotas que vierem a ser adicionadas.
"""

import re

from fastapi.testclient import TestClient

from app.main import app

# Públicas: exatamente estas. O registo e a config servem o ecrã de login (o registo tem limite por IP e pode ser desligado).
PUBLIC = {
    ("GET", "/api/health"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/register"),
    ("GET", "/api/auth/config"),
}


def test_todas_as_rotas_exigem_sessao():
    # app.openapi() é API pública e lista todas as rotas (app.routes esconde os routers incluídos)
    client = TestClient(app, raise_server_exceptions=False)
    checked = 0
    for route_path, ops in app.openapi()["paths"].items():
        path = re.sub(r"\{[^}]+\}", "1", route_path)
        for method in ops:
            if (method.upper(), route_path) in PUBLIC:
                continue
            r = client.request(method.upper(), path)
            assert r.status_code == 401, f"{method.upper()} {route_path} -> {r.status_code}"
            checked += 1
    assert checked >= 2  # /me e /logout; protege contra o teste ficar vazio


def test_docs_desligados_por_omissao():
    client = TestClient(app)
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
