import secrets
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import NamedTuple

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import SESSION_COOKIE, TRUSTED_PROXIES
from .db import SessionLocal
from .models import Sessao, Utilizador
from .security import hash_token

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db


class Auth(NamedTuple):
    utilizador: Utilizador
    sessao: Sessao


def client_ip(request: Request) -> str:
    """IP do cliente; só lê X-Forwarded-For quando o pedido vem de um proxy de confiança."""
    peer = request.client.host if request.client else "unknown"
    xff = request.headers.get("x-forwarded-for")
    if xff and peer in TRUSTED_PROXIES:
        return xff.split(",")[-1].strip()  # o último valor foi acrescentado pelo proxy de confiança
    return peer


def require_auth(request: Request, db: Session = Depends(get_db)) -> Auth:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(401, "Não autenticado")
    sessao = db.get(Sessao, hash_token(token))
    now = datetime.now(UTC)
    if sessao is None or sessao.expira_em <= now:
        raise HTTPException(401, "Sessão inválida ou expirada")
    user = db.get(Utilizador, sessao.utilizador_id)
    if user is None or not user.ativo:
        raise HTTPException(401, "Sessão inválida ou expirada")
    if request.method not in SAFE_METHODS:
        sent = request.headers.get("x-csrf-token", "")
        if not secrets.compare_digest(sent, sessao.csrf_token):
            raise HTTPException(403, "CSRF token em falta ou inválido")
    sessao.ultimo_uso_em = now
    db.commit()
    return Auth(user, sessao)
