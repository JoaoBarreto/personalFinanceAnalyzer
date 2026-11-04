"""Verifica se um extrato é aceite pelo parser de um banco, SEM mostrar valores nem descrições.

Imprime só: aceite/recusado, nº de movimentos, período, ordem, se os saldos reconciliam e nº de quebras. Se for
recusado, mostra os tipos de problema, contagens e linhas, com os exemplos «…» retirados (podem conter montantes).

Uso: backend/.venv/bin/python scripts/check_statement.py <banco> ficheiro [ficheiro ...]
     <banco> é um id do registo (backend/app/parsers/registry.py), p.ex. «bankinter».
"""

import os
import re
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
)

from app.parsers.base import ParseError  # noqa: E402
from app.parsers.registry import PARSERS, get_parser  # noqa: E402


def check(parser_id: str, path: str) -> None:
    parser = get_parser(parser_id)
    if parser is None:
        sys.exit(
            f"Banco desconhecido «{parser_id}». Disponíveis: {', '.join(sorted(PARSERS))}"
        )
    print(f"\n=== {os.path.basename(path)}  ({os.path.getsize(path)} bytes)")
    with open(path, "rb") as f:
        content = f.read()
    try:
        st = parser.parse(content)
    except ParseError as e:
        print("RECUSADO:")
        print(re.sub(r"«[^»]*»", "«…»", str(e)))
        return
    print("ACEITE")
    print("  movimentos:", len(st.movimentos))
    print("  período:", st.periodo_inicio, "a", st.periodo_fim)
    if st.movimentos:
        print(
            "  primeiro/último movimento:",
            st.movimentos[0].data_movimento,
            "/",
            st.movimentos[-1].data_movimento,
        )
    print(
        "  ordem no ficheiro:",
        st.ordem_ficheiro,
        "(ambígua)" if st.ordem_ambigua else "",
    )
    print(
        "  saldos reconciliam:",
        st.reconciliado,
        "| quebras na cadeia:",
        len(st.quebras),
    )
    print(
        "  dias distintos com movimentos:",
        len({m.data_movimento for m in st.movimentos}),
    )


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    for p in sys.argv[2:]:
        check(sys.argv[1], p)
