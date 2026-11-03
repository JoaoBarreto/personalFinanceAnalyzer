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
from decimal import Decimal

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


# Formatos numéricos aceites. O separador decimal é detetado UMA vez por ficheiro (nunca por célula, nem por omissão):
# um ficheiro com `-889.50` lido como se o ponto fosse separador de milhares dava -88950, e a reconciliação de
# saldos não o apanha porque multiplica montantes e saldos pelo mesmo fator.
_STYLE_RE = {
    "virgula": re.compile(r"^[+-]?(\d{1,3}(\.\d{3})+|\d+)(,\d{1,2})?$"),  # 1.234,56
    "ponto": re.compile(r"^[+-]?(\d{1,3}(,\d{3})+|\d+)(\.\d{1,2})?$"),  # 1,234.56
}


def _clean(s: str) -> str:
    return s.strip().replace(" ", "").replace("\u00a0", "")


def _vote(s: str) -> str | None:
    """'virgula' | 'ponto' se a célula decide o estilo; None se for ambígua (ex.: «1.234») ou um inteiro simples."""
    t = _clean(s).lstrip("+-")
    if not t or not re.fullmatch(r"[\d.,]+", t):
        raise ParseError(f"Número inválido: {s!r}")
    com, pon = "," in t, "." in t
    if com and pon:  # o último separador é o decimal
        return "virgula" if t.rfind(",") > t.rfind(".") else "ponto"
    if not (com or pon):
        return None
    sep = "," if com else "."
    if t.count(sep) > 1:  # separador repetido = milhares; o decimal (se existir) é o outro
        return "ponto" if sep == "," else "virgula"
    return ("virgula" if com else "ponto") if len(t.split(sep)[1]) in (1, 2) else None


def detect_number_style(values: list[str]) -> str:
    votes = {v for s in values if (v := _vote(s))}
    if len(votes) > 1:
        raise ParseError(
            "Formato numérico inconsistente no ficheiro (mistura vírgula e ponto como separador decimal)."
        )
    if votes:
        return votes.pop()
    if any(re.search(r"[.,]", _clean(s)) for s in values):
        raise ParseError(
            "Não foi possível determinar o separador decimal (valores como «1.234» são ambíguos). "
            "Exporte o ficheiro com casas decimais."
        )
    return "virgula"  # só inteiros simples: qualquer estilo dá o mesmo resultado


def _parse_amount(s: str, style: str) -> Decimal:
    t = _clean(s)
    if not _STYLE_RE[style].match(t):
        raise ParseError(f"Número inválido para o formato detetado ({style}): {s!r}")
    t = t.replace(".", "").replace(",", ".") if style == "virgula" else t.replace(",", "")
    return Decimal(t)


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

        cells: list[tuple[date, date | None, str, str, str]] = []
        for lineno, r in enumerate(rows[h + 1 :], start=h + 2):
            if not r or not _DATE_RE.match(r[0].strip()):
                break  # fim dos dados (linha em branco ou rodapé)
            if len(r) <= max(idx.values()):
                raise ParseError(f"Linha {lineno} com colunas a menos.")
            vd = r[idx["valor"]].strip()
            try:
                cells.append(
                    (
                        _parse_date(r[idx["mov"]]),
                        _parse_date(vd) if _DATE_RE.match(vd) else None,
                        r[idx["desc"]].strip(),
                        r[idx["montante"]],
                        r[idx["saldo"]],
                    )
                )
            except ValueError as e:
                raise ParseError(f"Linha {lineno}: {e}") from e

        if not cells:
            raise ParseError("Nenhum movimento encontrado.")
        style = detect_number_style([c[3] for c in cells] + [c[4] for c in cells])
        try:
            raw = [
                (dm, dv, desc, _parse_amount(m, style), _parse_amount(sd, style))
                for dm, dv, desc, m, sd in cells
            ]
        except ParseError as e:
            raise ParseError(f"{e}") from e

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
