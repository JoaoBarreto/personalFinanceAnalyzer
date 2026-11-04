from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ... import config
from ...config import SESSION_COOKIE, SESSION_TTL_DAYS
from ...deps import Auth, client_ip, get_db, require_auth
from ...models import Sessao, Utilizador
from ...rate_limit import is_blocked, record_failure, register_blocked, reset
from ...security import DUMMY_HASH, hash_token, new_token, verify_password
from ...services.users import NOME_MAX, PASSWORD_MAX, UserError, count_users, create_user, normalize_username

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


def _start_session(db: Session, user: Utilizador, request: Request, response: Response) -> MeOut:
    """Cria a sessão no servidor e põe o cookie (partilhado pelo login e pelo registo)."""
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


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = client_ip(request)
    if is_blocked(ip):
        raise HTTPException(429, "Demasiadas tentativas. Tenta mais tarde.")
    user = db.scalar(
        select(Utilizador)
        .where(func.lower(Utilizador.username) == normalize_username(body.username))
        .order_by(Utilizador.id)
    )
    ok = verify_password(user.password_hash if user else DUMMY_HASH, body.password)
    if not (user and user.ativo and ok):
        record_failure(ip)
        raise HTTPException(401, "Credenciais inválidas")
    reset(ip)
    return _start_session(db, user, request, response)


class ConfigOut(BaseModel):
    registo_aberto: bool
    sem_utilizadores: bool


@router.get("/config", response_model=ConfigOut)
def public_config(db: Session = Depends(get_db)):
    """Público: diz ao ecrã de login se pode mostrar «Criar conta» (e se é a primeira conta)."""
    vazio = count_users(db) == 0
    return ConfigOut(registo_aberto=vazio or config.ALLOW_REGISTRATION, sem_utilizadores=vazio)


class RegisterIn(BaseModel):
    username: str = Field(max_length=64)
    nome: str = Field(max_length=NOME_MAX * 2)
    password: str = Field(max_length=PASSWORD_MAX * 2)


@router.post("/register", response_model=MeOut, status_code=201)
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """Cria um utilizador novo (com as suas categorias) e inicia sessão. Aberto se não houver utilizadores ou se
    `ALLOW_REGISTRATION` estiver ligado; limitado por IP."""
    if register_blocked("reg:" + client_ip(request)):
        raise HTTPException(429, "Demasiadas tentativas de registo. Tente mais tarde.")
    if count_users(db) > 0 and not config.ALLOW_REGISTRATION:
        raise HTTPException(403, "O registo de novos utilizadores está desativado neste servidor.")
    try:
        user = create_user(db, body.username, body.nome, body.password)
        db.flush()
    except UserError as e:
        db.rollback()
        raise HTTPException(e.status, str(e)) from e
    except IntegrityError as e:  # duas inscrições em simultâneo com o mesmo nome
        db.rollback()
        raise HTTPException(409, "Esse nome de utilizador não está disponível.") from e
    return _start_session(db, user, request, response)


@router.get("/me", response_model=MeOut)
def me(auth: Auth = Depends(require_auth)):
    u, s = auth
    return MeOut(id=u.id, username=u.username, nome=u.nome, csrf_token=s.csrf_token)


@router.post("/logout", status_code=204)
def logout(response: Response, auth: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    db.execute(delete(Sessao).where(Sessao.token_hash == auth.sessao.token_hash))
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
