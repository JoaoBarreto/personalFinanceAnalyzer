"""Verifica se um extrato do Bankinter (.xls ou .csv) é aceite pela app, SEM mostrar valores nem descrições.

Imprime só: aceite/recusado, nº de movimentos, período, ordem, se os saldos reconciliam e nº de quebras. Se for
recusado, mostra os tipos de problema, contagens e linhas, com os exemplos «…» retirados (podem conter montantes).

Uso: backend/.venv/bin/python scripts/check_xls.py [ficheiro ...]   (sem argumentos: ~/Transferências e ~/Downloads)
"""

import glob
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from app.parsers.banks.bankinter.parser import BankinterParser  # noqa: E402
from app.parsers.base import ParseError  # noqa: E402


def check(path: str) -> None:
    print(f"\n=== {os.path.basename(path)}  ({os.path.getsize(path)} bytes)")
    with open(path, "rb") as f:
        content = f.read()
    try:
        st = BankinterParser().parse(content)
    except ParseError as e:
        print("RECUSADO:")
        print(re.sub(r"«[^»]*»", "«…»", str(e)))
        return
    print("ACEITE")
    print("  movimentos:", len(st.movimentos))
    print("  período:", st.periodo_inicio, "a", st.periodo_fim)
    print("  primeiro/último movimento:", st.movimentos[0].data_movimento, "/", st.movimentos[-1].data_movimento)
    print("  ordem no ficheiro:", st.ordem_ficheiro, "(ambígua)" if st.ordem_ambigua else "")
    print("  saldos reconciliam:", st.reconciliado, "| quebras na cadeia:", len(st.quebras))
    dias = len({m.data_movimento for m in st.movimentos})
    print("  dias distintos com movimentos:", dias)


if __name__ == "__main__":
    paths = sys.argv[1:] or sorted(
        p
        for d in ("~/Transferências", "~/Downloads")
        for ext in ("xls", "csv")
        for p in glob.glob(os.path.expanduser(f"{d}/ConsultaMovimentos*.{ext}"))
    )
    if not paths:
        sys.exit("Nenhum ficheiro encontrado; indique o caminho.")
    for p in paths:
        check(p)
