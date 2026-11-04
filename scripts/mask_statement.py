"""Mostra a ESTRUTURA de um extrato bancário (.xls, .xlsx ou .csv) com os valores mascarados.

Serve para analisar o formato de um banco novo SEM expor dados pessoais. Corre na máquina do utilizador, que cola
a saída para análise; ninguém precisa de abrir o ficheiro real. A mesma lógica está na app («Adicionar conta» →
outro banco), em backend/app/services/statement_mask.py.

Máscara: letras -> «x», dígitos -> «9»; pontuação e separadores ficam (mostram o formato de datas e números).
Só se mostram sem máscara palavras de um vocabulário genérico de extratos (data, valor, montante, saldo, …) nos
nomes de colunas e nos rótulos do preâmbulo. `--mostrar-rotulos` mostra TODOS os nomes de colunas e rótulos: use só
depois de confirmar que a linha do cabeçalho não tem dados pessoais.

Uso: backend/.venv/bin/python scripts/mask_statement.py [--mostrar-rotulos] ficheiro [ficheiro ...]
(.xlsx precisa de openpyxl; PDF não é suportado: peça ao banco o .xls/.xlsx/.csv.)
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from app.services.statement_mask import UnsupportedFormat, describe_bytes  # noqa: E402


def describe(path: str, show_all: bool) -> None:
    with open(path, "rb") as f:
        content = f.read()
    print(f"\n=== {os.path.basename(path)}")
    try:
        print(describe_bytes(content, show_all))
    except UnsupportedFormat as e:
        sys.exit(str(e))


if __name__ == "__main__":
    args = sys.argv[1:]
    show_all = "--mostrar-rotulos" in args
    paths = [a for a in args if not a.startswith("--")]
    if not paths:
        sys.exit(__doc__)
    for p in paths:
        describe(p, show_all)
