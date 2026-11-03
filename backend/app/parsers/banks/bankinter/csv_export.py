"""Parser da exportação CSV de movimentos do Bankinter (homebanking).

Layout observado (validar com novos exports): linhas de cabeçalho livres, uma linha de colunas
`Data Movimento,Data Valor,Descrição,Transacção,Montante,Moeda,Saldo,...`, linhas de dados com datas
`dd-mm-aaaa` e números `"1234,56"`, e um rodapé legal. Não se assume nº fixo de linhas de cabeçalho.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from ...base import ParsedMovement, ParsedStatement, ParseError
from ...reconcile import chronological_breaks, detect_order

BANK_ID = "bankinter_csv"
_DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")
_PERIOD_RE = re.compile(r"(\d{2}-\d{2}-\d{4})\s*a\s*(\d{2}-\d{2}-\d{4})")
_CURRENCY_RE = re.compile(r"\(\s*([A-Z]{3})\s*\)")
_REQUIRED = ("data movimento", "data valor", "descri", "montante", "saldo")


def _decode(content: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ParseError("Não foi possível descodificar o ficheiro (esperado UTF-8 ou CP1252).")


def _parse_date(s: str) -> date:
    return datetime.strptime(s.strip(), "%d-%m-%Y").date()


def _parse_amount(s: str) -> Decimal:
    try:
        return Decimal(s.strip().replace(".", "").replace(" ", "").replace(",", "."))
    except InvalidOperation as e:
        raise ParseError(f"Número inválido: {s!r}") from e


def _rows(text: str) -> list[list[str]]:
    sample = text[:4096]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    return list(csv.reader(io.StringIO(text), delimiter=delimiter))


def _find_header(rows: list[list[str]]) -> int | None:
    for i, r in enumerate(rows):
        cells = [c.strip().lower() for c in r]
        if cells and cells[0] == "data movimento" and all(any(k in c for c in cells) for k in _REQUIRED):
            return i
    return None


class BankinterCsvParser:
    bank_id = BANK_ID

    def can_parse(self, content: bytes) -> float:
        try:
            return 1.0 if _find_header(_rows(_decode(content))) is not None else 0.0
        except ParseError:
            return 0.0

    def parse(self, content: bytes) -> ParsedStatement:
        rows = _rows(_decode(content))
        h = _find_header(rows)
        if h is None:
            raise ParseError(
                "Cabeçalho 'Data Movimento' não encontrado: não parece uma exportação Bankinter."
            )
        cols = [c.strip().lower() for c in rows[h]]
        idx = {
            "mov": cols.index("data movimento"),
            "valor": cols.index("data valor"),
            "desc": next(i for i, c in enumerate(cols) if c.startswith("descri")),
            "montante": cols.index("montante"),
            "saldo": cols.index("saldo"),
        }

        moeda = periodo_inicio = periodo_fim = None
        for r in rows[:h]:
            line = " ".join(r)
            if moeda is None and (m := _CURRENCY_RE.search(line)):
                moeda = m.group(1)
            if periodo_inicio is None and (m := _PERIOD_RE.search(line)):
                periodo_inicio, periodo_fim = _parse_date(m.group(1)), _parse_date(m.group(2))

        raw: list[tuple[date, date | None, str, Decimal, Decimal]] = []
        for lineno, r in enumerate(rows[h + 1 :], start=h + 2):
            if not r or not _DATE_RE.match(r[0].strip()):
                break  # fim dos dados (linha em branco ou rodapé)
            if len(r) <= max(idx.values()):
                raise ParseError(f"Linha {lineno} com colunas a menos.")
            vd = r[idx["valor"]].strip()
            try:
                raw.append(
                    (
                        _parse_date(r[idx["mov"]]),
                        _parse_date(vd) if _DATE_RE.match(vd) else None,
                        r[idx["desc"]].strip(),
                        _parse_amount(r[idx["montante"]]),
                        _parse_amount(r[idx["saldo"]]),
                    )
                )
            except ValueError as e:
                raise ParseError(f"Linha {lineno}: {e}") from e

        if not raw:
            raise ParseError("Nenhum movimento encontrado.")

        ordem, ambigua = detect_order([(r[3], r[4]) for r in raw])
        chrono = raw if ordem == "asc" else raw[::-1]

        movimentos: list[ParsedMovement] = []
        counter: dict[date, int] = {}
        for dm, dv, desc, montante, saldo in chrono:
            n = counter.get(dm, 0)
            counter[dm] = n + 1
            movimentos.append(ParsedMovement(dm, dv, desc, montante, saldo, n))

        return ParsedStatement(
            moeda=moeda,
            periodo_inicio=periodo_inicio or movimentos[0].data_movimento,
            periodo_fim=periodo_fim or movimentos[-1].data_movimento,
            ordem_ficheiro=ordem,
            ordem_ambigua=ambigua,
            saldo_inicial=chrono[0][4] - chrono[0][3],
            saldo_final=chrono[-1][4],
            movimentos=movimentos,
            quebras=chronological_breaks([(r[3], r[4]) for r in chrono]),
        )
