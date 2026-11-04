"""Leitura de folhas (.xls, .xlsx, .csv) para uma grelha de células tipadas, sem adivinhar nada.

Célula = (tipo, valor): «texto» (str), «num» (float/int), «data» (datetime) ou «vazio». O CSV vem sempre como texto.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from ..base import ParseError

Cell = tuple[str, Any]
EMPTY: Cell = ("vazio", "")
OLE = bytes.fromhex("d0cf11e0a1b11ae1")


def sniff(content: bytes) -> str:
    """«xls» | «xlsx» | «pdf» | «html» | «csv» pela assinatura do conteúdo (não pela extensão)."""
    if content.startswith(OLE):
        return "xls"
    if content.startswith(b"PK\x03\x04"):
        return "xlsx"
    if content.startswith(b"%PDF"):
        return "pdf"
    if content.lstrip()[:1] == b"<":
        return "html"
    return "csv"


def read_grid(
    content: bytes, formato: str, codificacao: str | None = None, separador: str | None = None
) -> list[list[Cell]]:
    if sniff(content) != formato:
        raise ParseError(f"O ficheiro não é do tipo esperado para esta conta ({formato}).")
    if formato == "xls":
        return _xls(content)
    if formato == "xlsx":
        return _xlsx(content)
    return _csv(content, codificacao or "utf-8-sig", separador or ",")


def _xls(content: bytes) -> list[list[Cell]]:
    import xlrd

    try:
        book = xlrd.open_workbook(file_contents=content)
    except Exception as e:
        raise ParseError("Não foi possível ler o ficheiro como .xls (Excel 97-2003).") from e
    if book.nsheets != 1:
        raise ParseError(f"O ficheiro tem {book.nsheets} folhas; o modelo desta conta espera 1.")
    sh = book.sheet_by_index(0)
    rows: list[list[Cell]] = []
    for r in range(sh.nrows):
        row: list[Cell] = []
        for c in range(sh.ncols):
            cell = sh.cell(r, c)
            if cell.ctype == xlrd.XL_CELL_TEXT:
                s = cell.value.strip()
                row.append(("texto", s) if s else EMPTY)
            elif cell.ctype == xlrd.XL_CELL_NUMBER:
                row.append(("num", cell.value))
            elif cell.ctype == xlrd.XL_CELL_DATE:
                row.append(("data", xlrd.xldate.xldate_as_datetime(cell.value, book.datemode)))
            elif cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                row.append(EMPTY)
            else:
                raise ParseError(f"Célula inesperada (tipo {cell.ctype}) na linha {r + 1}.")
        rows.append(row)
    return rows


def _xlsx(content: bytes) -> list[list[Cell]]:
    try:
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except Exception as e:
        raise ParseError("Não foi possível ler o ficheiro como .xlsx.") from e
    if len(wb.worksheets) != 1:
        raise ParseError(f"O ficheiro tem {len(wb.worksheets)} folhas; o modelo desta conta espera 1.")
    rows: list[list[Cell]] = []
    for r in wb.worksheets[0].iter_rows(values_only=True):
        row: list[Cell] = []
        for v in r:
            if v is None or (isinstance(v, str) and not v.strip()):
                row.append(EMPTY)
            elif isinstance(v, bool):
                raise ParseError("Célula booleana inesperada no extrato.")
            elif isinstance(v, (int, float)):
                row.append(("num", v))
            elif hasattr(v, "year"):
                row.append(("data", v))
            else:
                row.append(("texto", str(v).strip()))
        rows.append(row)
    return rows


def _csv(content: bytes, codificacao: str, separador: str) -> list[list[Cell]]:
    try:
        text = content.decode(codificacao)
    except UnicodeDecodeError as e:
        raise ParseError(f"O ficheiro não está em {codificacao}, como o modelo desta conta exige.") from e
    return [
        [("texto", c.strip()) if c.strip() else EMPTY for c in line]
        for line in csv.reader(io.StringIO(text), delimiter=separador)
    ]
