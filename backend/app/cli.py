"""CLI: `python -m app.cli create-user <username> --nome "Nome"` (pede a password sem eco)."""

import argparse
import getpass
import sys

from sqlalchemy import select

from .db import SessionLocal
from .models import Utilizador
from .security import hash_password


def create_user(username: str, nome: str, password: str) -> None:
    if len(password) < 10:
        raise SystemExit("A password deve ter pelo menos 10 caracteres.")
    with SessionLocal() as db:
        if db.scalar(select(Utilizador).where(Utilizador.username == username)):
            raise SystemExit(f"O utilizador {username!r} já existe.")
        db.add(Utilizador(username=username, nome=nome, password_hash=hash_password(password)))
        db.commit()


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-user")
    c.add_argument("username")
    c.add_argument("--nome", required=True)
    c.add_argument("--password-stdin", action="store_true", help="ler a password do stdin (não interativo)")
    args = p.parse_args(argv)
    if args.password_stdin:
        pw = sys.stdin.readline().rstrip("\n")
    else:
        pw = getpass.getpass("Password: ")
        if pw != getpass.getpass("Repetir password: "):
            raise SystemExit("As passwords não coincidem.")
    create_user(args.username, args.nome, pw)
    print(f"Utilizador {args.username!r} criado.", file=sys.stderr)


if __name__ == "__main__":
    main()
