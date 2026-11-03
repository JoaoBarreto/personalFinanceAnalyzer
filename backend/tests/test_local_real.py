"""Corre só se existir um export real em tests/fixtures/local/ (ignorado pelo git)."""

from pathlib import Path

import pytest

from app.parsers.banks.bankinter.csv_export import BankinterCsvParser

FILES = sorted((Path(__file__).parent / "fixtures/local").glob("*.csv"))


@pytest.mark.skipif(not FILES, reason="sem exports reais locais")
@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_export_real_reconcilia(path):
    s = BankinterCsvParser().parse(path.read_bytes())
    assert s.movimentos and s.reconciliado and s.diferenca == 0
