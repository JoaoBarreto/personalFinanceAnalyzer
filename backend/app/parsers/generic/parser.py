"""Parser ESTRITO guiado por um Template (extratos de qualquer banco com folha tabular e coluna de saldo).

Tão rígido como o do Bankinter: cabeçalho igual ao do modelo (nome e ordem), datas só no formato do modelo,
montantes com exatamente 2 casas e os separadores do modelo, uma só folha, nada de dados depois do fim, e a cadeia
de saldos é a rede de segurança. Qualquer desvio recusa o ficheiro inteiro, sem importar nada.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from ..base import ParsedStatement, ParseError
from ..build import build_statement
from ..money import cents
from .reader import EMPTY, Cell, read_grid, sniff
from .template import Template

DATE_SHAPE = re.compile(r"^\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}$")  # parece data (em qualquer formato)
_DATE_FORMATS: dict[str, tuple[re.Pattern[str], str]] = {
    "dd-mm-aaaa": (re.compile(r"^(\d{2})-(\d{2})-(\d{4})$"), "dmy"),
    "dd/mm/aaaa": (re.compile(r"^(\d{2})/(\d{2})/(\d{4})$"), "dmy"),
    "dd.mm.aaaa": (re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$"), "dmy"),
    "aaaa-mm-dd": (re.compile(r"^(\d{4})-(\d{2})-(\d{2})$"), "ymd"),
    "aaaa/mm/dd": (re.compile(r"^(\d{4})/(\d{2})/(\d{2})$"), "ymd"),
    "mm/dd/aaaa": (re.compile(r"^(\d{2})/(\d{2})/(\d{4})$"), "mdy"),
}
_INT = {
    "nenhum": r"\d+",
    "ponto": r"\d{1,3}(?:\.\d{3})*",
    "virgula": r"\d{1,3}(?:,\d{3})*",
    "espaco": r"\d{1,3}(?:[   ]\d{3})*",
}
HINT = (
    "Use o ficheiro original exportado do homebanking, sem o abrir e voltar a guardar noutra aplicação, "
    "ou corrija o ficheiro e carregue-o de novo."
)


def parse_date_text(s: str, formato: str) -> date | None:
    """None se `s` não tem EXATAMENTE o formato; ValueError se tem o formato mas não é uma data real."""
    rx, order = _DATE_FORMATS[formato]
    m = rx.match(s)
    if not m:
        return None
    a, b, c = (int(x) for x in m.groups())
    d, mo, y = {"dmy": (a, b, c), "ymd": (c, b, a), "mdy": (b, a, c)}[order]
    return date(y, mo, d)


def amount_regex(decimal: str, milhares: str) -> re.Pattern[str]:
    return re.compile(rf"^(-?)({_INT[milhares]}){re.escape(decimal)}(\d{{2}})$")


def to_money(cell: Cell, t: Template) -> Decimal:
    kind, v = cell
    if kind == "num":
        d = cents(float(v))
        if d is None:
            raise ValueError("mais de 2 casas decimais")
        return d
    if kind != "texto":
        raise ValueError("não é um valor numérico")
    m = amount_regex(t.decimal, t.milhares).match(v)
    if not m:
        raise ValueError(f"não corresponde ao modelo (decimal «{t.decimal}», milhares {t.milhares}, 2 casas)")
    sign, inteiro, frac = m.groups()
    return Decimal(f"{sign}{re.sub(r'[^0-9]', '', inteiro)}.{frac}")


class GenericParser:
    bank_id = "generico"

    def __init__(self, template: Template):
        self.t = template

    def can_parse(self, content: bytes) -> float:
        return 1.0 if sniff(content) == self.t.formato else 0.0

    def _fail(self, problems: list[str]) -> ParseError:
        return ParseError(
            "O ficheiro não está de acordo com o modelo guardado para esta conta e não foi importado:\n• "
            + "\n• ".join(problems)
            + f"\n{HINT}"
        )

    def parse(self, content: bytes) -> ParsedStatement:
        t = self.t
        try:
            grid = read_grid(content, t.formato, t.codificacao, t.separador)
        except ParseError as e:
            raise self._fail([str(e)]) from e
        want = [c.strip().casefold() for c in t.cabecalho]
        header = None
        for i, row in enumerate(grid):
            names = [str(v).strip().casefold() if k != "vazio" else "" for k, v in row]
            while names and not names[-1]:
                names.pop()
            if names == want:
                header = i
                break
        if header is None:
            raise self._fail(
                [
                    "Não encontrei a linha de colunas do modelo.",
                    "Esperado: " + ", ".join(t.cabecalho) + ".",
                ]
            )
        idx = {name: i for i, name in enumerate(want)}

        def col(name: str | None) -> int | None:
            return None if name is None else idx[name.strip().casefold()]

        c_data, c_valor, c_saldo = col(t.data), col(t.data_valor), col(t.saldo)
        c_mont, c_deb, c_cred = col(t.montante), col(t.debito), col(t.credito)
        c_desc = [col(n) for n in t.descricao]

        agg: dict[str, dict] = {}

        def bad(key: str, texto: str, lineno: int, ex: str = "") -> None:
            a = agg.setdefault(key, {"n": 0, "linha": lineno, "ex": ex, "texto": texto})
            a["n"] += 1

        def cell(row: list[Cell], i: int) -> Cell:
            return row[i] if i < len(row) else EMPTY

        def is_date_like(row: list[Cell]) -> bool:
            k, v = cell(row, c_data)
            return k == "data" or (k == "texto" and bool(DATE_SHAPE.match(v)))

        def read_date(c: Cell, what: str, lineno: int) -> date | None:
            k, v = c
            if k == "data":
                if not t.celulas_data_nativas:
                    bad(
                        "excel_date",
                        f"{what} é uma data do Excel (o modelo espera texto {t.formato_data})",
                        lineno,
                    )
                    return None
                return v.date() if hasattr(v, "date") else v
            if k != "texto":
                bad(f"{what}:tipo", f"{what} não é uma data", lineno, str(v))
                return None
            try:
                d = parse_date_text(v, t.formato_data)
            except ValueError:
                bad("data_invalida", f"{what} inválida (dia ou mês inexistente)", lineno, v)
                return None
            if d is None:
                bad("data_fmt", f"{what} num formato inesperado (esperado {t.formato_data})", lineno, v)
            return d

        raw: list[tuple[date, date | None, str, Decimal, Decimal]] = []
        ended = False
        for lineno, row in enumerate(grid[header + 1 :], start=header + 2):
            if ended:
                if is_date_like(row):
                    bad("depois_do_fim", "Linhas com data depois de uma linha que não é movimento", lineno)
                continue
            if not is_date_like(row):
                ended = True  # fim dos dados (linha em branco ou rodapé)
                continue
            dm = read_date(cell(row, c_data), "Data", lineno)
            dv = None
            if c_valor is not None and cell(row, c_valor)[0] != "vazio":
                dv = read_date(cell(row, c_valor), "Data valor", lineno)
            ok = dm is not None
            try:
                if c_mont is not None:
                    montante = to_money(cell(row, c_mont), t)
                else:
                    deb, cred = cell(row, c_deb), cell(row, c_cred)
                    d_ = None if deb[0] == "vazio" else to_money(deb, t)
                    c_ = None if cred[0] == "vazio" else to_money(cred, t)
                    if (d_ or 0) != 0 and (c_ or 0) != 0:
                        raise ValueError("débito e crédito preenchidos na mesma linha")
                    if d_ is None and c_ is None:
                        raise ValueError("sem débito nem crédito")
                    debito = d_ or Decimal(0)
                    montante = (c_ or Decimal(0)) + (-debito if t.sinal_debito == "positivo" else debito)
                if montante == 0:
                    raise ValueError("montante zero")
            except ValueError as e:
                bad(
                    f"montante:{e}",
                    f"Montante: {e}",
                    lineno,
                    str(cell(row, c_mont if c_mont is not None else c_deb)[1]),
                )
                ok = False
            try:
                saldo = to_money(cell(row, c_saldo), t)
            except ValueError as e:
                bad(f"saldo:{e}", f"Saldo: {e}", lineno, str(cell(row, c_saldo)[1]))
                ok = False
            desc = " ".join(str(cell(row, i)[1]) for i in c_desc if cell(row, i)[0] != "vazio")
            if ok and dm is not None:
                raw.append((dm, dv, desc, montante, saldo))

        if raw and not agg:
            dates = [r[0] for r in raw]
            if dates != sorted(dates) and dates != sorted(dates, reverse=True):
                bad("ordem_datas", "As datas não estão em ordem (nem crescente nem decrescente)", 0)
        if agg:
            raise self._fail(
                [
                    f"{a['texto']} — {a['n']} ocorrência(s)"
                    + (f"; primeira na linha {a['linha']}" if a["linha"] else "")
                    + (f", «{a['ex']}»" if a["ex"] else "")
                    + "."
                    for a in agg.values()
                ]
            )
        if not raw:
            raise self._fail(["Nenhum movimento encontrado depois da linha de colunas."])
        return build_statement(raw, t.moeda, None, None)
