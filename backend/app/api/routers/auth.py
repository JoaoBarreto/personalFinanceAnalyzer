from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ... import config
from ...config import SESSION_COOKIE, SESSION_TTL_DAYS
from ...deps import Auth, client_ip, get_db, require_auth
from ...models import Sessao, Utilizador
from ...rate_limit import is_blocked, record_failure, reset
from ...security import DUMMY_HASH, hash_token, new_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def cookie_secure(request: Request) -> bool:
    """Cookie `Secure` conforme o modo: «true»/«false» forçam; «auto» só quando o acesso é por HTTPS.

    Por HTTPS = esquema https, `X-Forwarded-Proto: https` (proxy) ou um nome `*.ts.net` (tailscale serve). Assim o
    acesso pelo Tailscale continua com cookie Secure, e o acesso por HTTP na rede de casa (opt-in) consegue iniciar
    sessão em vez de falhar em silêncio, porque o browser rejeitaria um cookie Secure recebido por http.
    """
    mode = config.COOKIE_SECURE_MODE
    if mode in ("true", "1", "yes"):
        return True
    if mode in ("false", "0", "no"):
        return False
    host = request.headers.get("host", "").split(":")[0].lower()
    return (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto", "").lower() == "https"
        or host.endswith(".ts.net")
    )


class LoginIn(BaseModel):
    username: str
    password: str


class MeOut(BaseModel):
    id: int
    username: str
    nome: str
    csrf_token: str


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = client_ip(request)
    if is_blocked(ip):
        raise HTTPException(429, "Demasiadas tentativas. Tenta mais tarde.")
    user = db.scalar(select(Utilizador).where(Utilizador.username == body.username))
    ok = verify_password(user.password_hash if user else DUMMY_HASH, body.password)
    if not (user and user.ativo and ok):
        record_failure(ip)
        raise HTTPException(401, "Credenciais inválidas")
    reset(ip)
    now = datetime.now(UTC)
    db.execute(delete(Sessao).where(Sessao.expira_em <= now))  # limpeza oportunista
    token, csrf = new_token(), new_token()
    db.add(
        Sessao(
            token_hash=hash_token(token),
            utilizador_id=user.id,
            csrf_token=csrf,
            expira_em=now + timedelta(days=SESSION_TTL_DAYS),
        )
    )
    db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_TTL_DAYS * 86400,
        httponly=True,
        secure=cookie_secure(request),
        samesite="lax",
        path="/",
    )
    return MeOut(id=user.id, username=user.username, nome=user.nome, csrf_token=csrf)


@router.get("/me", response_model=MeOut)
def me(auth: Auth = Depends(require_auth)):
    u, s = auth
    return MeOut(id=u.id, username=u.username, nome=u.nome, csrf_token=s.csrf_token)


@router.post("/logout", status_code=204)
def logout(response: Response, auth: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    db.execute(delete(Sessao).where(Sessao.token_hash == auth.sessao.token_hash))
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
