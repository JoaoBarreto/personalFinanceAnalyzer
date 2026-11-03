"""Leitor ESTRITO do .xls (Excel 97-2003) exportado pelo homebanking do Bankinter.

Estrutura real (confirmada no export do utilizador): 1 folha; preâmbulo em texto na coluna A (conta, período);
linha de colunas «Data Movimento … Data Taxa Câmbio» na linha 8; datas como TEXTO «dd-mm-aaaa»; Montante e Saldo como
NÚMEROS (formato 0.00, nunca mais de 2 casas decimais); linha em branco e rodapé legal no fim.

Cada linha da folha é convertida para o mesmo texto canónico do CSV («-889,50») e validada pelas MESMAS regras
(`parse_rows`). Os montantes são números binários (float): converte-se por cêntimos inteiros, nunca com Decimal(float).
Qualquer desvio (datas do Excel, montantes em texto, >2 casas, mais de 1 folha, colunas alteradas) é recusado: é o
sinal típico de o ficheiro ter sido aberto e guardado noutra aplicação.
"""

from __future__ import annotations

import math
from decimal import Decimal

import xlrd

from ...base import ParsedStatement
from .csv_export import _DATE_LIKE_RE, _DATE_RE, EXPECTED_HEADER, _fail, parse_rows

OLE_SIGNATURE = bytes.fromhex("d0cf11e0a1b11ae1")  # contentor binário do .xls
_IDX = {name: i for i, name in enumerate(c.casefold() for c in EXPECTED_HEADER)}
_TEXT_COLS = ("data movimento", "data valor", "descrição", "moeda")
_NUM_COLS = ("montante", "saldo")


def is_xls(content: bytes) -> bool:
    return content.startswith(OLE_SIGNATURE)


def _cents(v: float) -> Decimal | None:
    """Valor com exatamente até 2 casas, como Decimal exato; None se tiver mais (ou não for finito)."""
    c = v * 100
    if not math.isfinite(c) or abs(c) > 1e15 or abs(c - round(c)) > 1e-6:
        return None
    return Decimal(round(c)).scaleb(-2)


def _text(cell: xlrd.sheet.Cell) -> str:
    return cell.value.strip() if cell.ctype == xlrd.XL_CELL_TEXT else ""


def parse_xls(content: bytes) -> ParsedStatement:
    try:
        book = xlrd.open_workbook(file_contents=content)
    except Exception as e:
        raise _fail(["Não foi possível ler o ficheiro como .xls (Excel 97-2003)."]) from e
    if book.nsheets != 1:
        raise _fail([f"O ficheiro tem {book.nsheets} folhas; o export do Bankinter tem 1."])
    sheet = book.sheet_by_index(0)

    agg: dict[str, dict] = {}

    def bad(key: str, texto: str, lineno: int, ex: str = "") -> None:
        a = agg.setdefault(key, {"n": 0, "linha": lineno, "ex": ex, "texto": texto})
        a["n"] += 1

    header = next(
        (r for r in range(sheet.nrows) if _text(sheet.cell(r, 0)).casefold() == "data movimento"), None
    )
    rows: list[list[str]] = []
    in_data = header is not None
    for r in range(sheet.nrows):
        cells = sheet.row(r)
        out = [""] * sheet.ncols
        first = _text(cells[0]) if cells else ""
        is_data = (
            in_data
            and r > (header or 0)
            and (
                bool(_DATE_RE.match(first) or _DATE_LIKE_RE.match(first))
                or (
                    bool(cells) and cells[0].ctype == xlrd.XL_CELL_DATE
                )  # data do Excel: linha de dados, com problema
            )
        )
        if in_data and r > (header or 0) and not is_data:
            in_data = False  # a partir daqui é rodapé: só se lê texto
        for c, cell in enumerate(cells):
            if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                continue
            if not is_data:
                out[c] = str(cell.value).strip() if cell.ctype == xlrd.XL_CELL_TEXT else str(cell.value)
                continue
            name = next((n for n, i in _IDX.items() if i == c), None)
            if name in _NUM_COLS:
                if cell.ctype != xlrd.XL_CELL_NUMBER:
                    bad(
                        f"{name}:tipo",
                        f"{name.capitalize()} não é um número (esperado célula numérica)",
                        r + 1,
                    )
                    continue
                d = _cents(cell.value)
                if d is None:
                    bad(f"{name}:casas", f"{name.capitalize()} com mais de 2 casas decimais", r + 1)
                    continue
                out[c] = f"{d:.2f}".replace(".", ",")
            elif name in _TEXT_COLS:
                if cell.ctype == xlrd.XL_CELL_DATE:
                    bad(
                        "excel_date",
                        f"{EXPECTED_HEADER[c]} é uma data do Excel (esperado texto dd-mm-aaaa): o ficheiro foi "
                        "provavelmente guardado por outra aplicação",
                        r + 1,
                    )
                elif cell.ctype != xlrd.XL_CELL_TEXT:
                    bad(f"{name}:tipo", f"{EXPECTED_HEADER[c]} não é texto", r + 1)
                else:
                    out[c] = cell.value.strip()
            else:
                out[c] = str(cell.value).strip() if cell.ctype == xlrd.XL_CELL_TEXT else str(cell.value)
        rows.append(out)

    if agg:
        raise _fail(
            [f"{a['texto']} — {a['n']} ocorrência(s); primeira na linha {a['linha']}." for a in agg.values()]
        )
    return parse_rows(rows)
