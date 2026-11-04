"""CLI: `create-user <username> --nome "Nome"` (pede a password sem eco) e `reset-movements`."""

import argparse
import getpass
import sys

from sqlalchemy import select

from .db import SessionLocal
from .models import Utilizador
from .security import hash_password
from .services import reset
from .services.category_seed import seed_categories


def create_user(username: str, nome: str, password: str) -> None:
    if len(password) < 10:
        raise SystemExit("A password deve ter pelo menos 10 caracteres.")
    with SessionLocal() as db:
        if db.scalar(select(Utilizador).where(Utilizador.username == username)):
            raise SystemExit(f"O utilizador {username!r} já existe.")
        user = Utilizador(username=username, nome=nome, password_hash=hash_password(password))
        db.add(user)
        db.flush()
        seed_categories(db, user.id)  # cada utilizador tem as suas categorias
        db.commit()


def reset_movements(username: str, yes: bool) -> None:
    with SessionLocal() as db:
        user = db.scalar(select(Utilizador).where(Utilizador.username == username))
        if user is None:
            raise SystemExit(f"O utilizador {username!r} não existe.")
        n = reset.preview(db, user.id)
        print(
            f"Vai apagar {n['movimentos']} movimentos e {n['importacoes']} importações de {username!r}.\n"
            f"As categorias, as regras, as contas e os utilizadores ficam.\n"
            f"As {n['categorizacoes_manuais']} categorizações feitas à mão ficam guardadas linha a linha "
            f"(data + descrição) e reaplicam-se tal como estão quando reimportar o extrato"
            + (
                f"; {n['descricoes_com_excecoes']} descrição(ões) têm categorias diferentes em linhas diferentes e mantêm-nas."
                if n["descricoes_com_excecoes"]
                else "."
            ),
            file=sys.stderr,
        )
        if not yes and input("Escreva APAGAR para confirmar: ").strip() != "APAGAR":
            raise SystemExit("Cancelado. Nada foi alterado.")
        r = reset.reset_movements(db, user.id)
    print(
        f"Feito: {r['movimentos_apagados']} movimentos e {r['importacoes_apagadas']} importações apagados; "
        f"{r['categorizacoes_guardadas']} categorizações manuais guardadas. "
        "Importe agora o extrato (.xls) do homebanking.",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-user")
    c.add_argument("username")
    c.add_argument("--nome", required=True)
    c.add_argument("--password-stdin", action="store_true", help="ler a password do stdin (não interativo)")
    r = sub.add_parser("reset-movements", help="apaga movimentos e importações, mantendo categorias e regras")
    r.add_argument("--username", required=True, help="utilizador cujos movimentos são apagados (só os dele)")
    r.add_argument("--yes", action="store_true", help="não pedir confirmação")
    args = p.parse_args(argv)
    if args.cmd == "reset-movements":
        reset_movements(args.username, args.yes)
        return
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
