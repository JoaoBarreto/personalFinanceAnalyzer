"""Atalho para `check_statement.py bankinter ...` (mantido por compatibilidade).

Uso: backend/.venv/bin/python scripts/check_xls.py ficheiro [ficheiro ...]
"""

import os
import runpy
import sys

if len(sys.argv) < 2:
    sys.exit(__doc__)
sys.argv = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "check_statement.py"),
    "bankinter",
    *sys.argv[1:],
]
runpy.run_path(sys.argv[0], run_name="__main__")
