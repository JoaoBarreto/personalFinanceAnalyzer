"""Criação de utilizadores: o único caminho, usado pelo registo na web e pela CLI (`create-user`).

Cada utilizador recebe, na mesma transação, a sua cópia das categorias iniciais.
"""

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Utilizador
from ..security import hash_password
from .category_seed import seed_categories

USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,32}$")
PASSWORD_MIN, PASSWORD_MAX = 10, 256
NOME_MAX = 80


class UserError(ValueError):
    """Pedido de criação inválido; `status` é o código HTTP sugerido (422 dados inválidos, 409 nome em uso)."""

    def __init__(self, msg: str, status: int = 422):
        super().__init__(msg)
        self.status = status


def normalize_username(username: str) -> str:
    return username.strip().lower()


def count_users(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Utilizador)) or 0


def create_user(db: Session, username: str, nome: str, password: str) -> Utilizador:
    """Valida, cria o utilizador e semeia as suas categorias. Não faz commit (quem chama decide)."""
    username = normalize_username(username)
    nome = nome.strip()
    if not USERNAME_RE.match(username):
        raise UserError(
            "O nome de utilizador deve ter 3 a 32 caracteres: letras minúsculas, números, ponto, hífen ou _."
        )
    if not nome or len(nome) > NOME_MAX:
        raise UserError(f"O nome a mostrar é obrigatório (máx. {NOME_MAX} caracteres).")
    if not (PASSWORD_MIN <= len(password) <= PASSWORD_MAX):
        raise UserError(f"A palavra-passe deve ter entre {PASSWORD_MIN} e {PASSWORD_MAX} caracteres.")
    if db.scalar(select(Utilizador.id).where(func.lower(Utilizador.username) == username)):
        raise UserError("Esse nome de utilizador não está disponível.", status=409)
    user = Utilizador(username=username, nome=nome, password_hash=hash_password(password))
    db.add(user)
    db.flush()
    seed_categories(db, user.id)
    return user
