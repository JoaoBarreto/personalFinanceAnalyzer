"""Parser ESTRITO da exportação CSV de movimentos do Bankinter (homebanking).

Aceita apenas o modelo do export original; qualquer desvio é recusado com uma mensagem a explicar o que está
errado (nunca se adivinha o formato). Modelo (confirmado com o ficheiro real):
  - UTF-8 (BOM opcional), separador de campos «,», quebras de linha \n ou \r\n;
  - linha de colunas exata: Data Movimento, Data Valor, Descrição, Transacção, Montante, Moeda, Saldo,
    Taxa Câmbio, Data Taxa Câmbio (nº de linhas de cabeçalho livre, o resto do preâmbulo é ignorado);
  - datas dd-mm-aaaa; montante e saldo com vírgula decimal, exatamente 2 casas e SEM separador de milhares
    (ex.: "-889,50", "38293,30"); moeda EUR; rodapé legal ignorado.
Motivo: um CSV aberto e guardado noutra aplicação (Excel, LibreOffice, Google Sheets) passa a usar ponto decimal,
«;» ou outra codificação, e um valor «-889.50» lido como milhares dava -88950, que a reconciliação de saldos não
apanha (escala uniforme em montantes e saldos).
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal

from ...base import ParsedStatement, ParseError
from ...build import build_statement

BANK_ID = "bankinter_csv"
EXPECTED_HEADER = (
    "Data Movimento", "Data Valor", "Descrição", "Transacção", "Montante", "Moeda", "Saldo",
    "Taxa Câmbio", "Data Taxa Câmbio",
)  # fmt: skip
_DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")
_DATE_LIKE_RE = re.compile(r"^\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}$")  # parece data mas noutro formato
_AMOUNT_RE = re.compile(r"^-?\d+,\d{2}$")
_PERIOD_RE = re.compile(r"(\d{2}-\d{2}-\d{4})\s*a\s*(\d{2}-\d{2}-\d{4})")
_CURRENCY_RE = re.compile(r"\(\s*([A-Z]{3})\s*\)")
_MAX_PROBLEMS = 8
HINT = (
    "Use o ficheiro .xls original exportado do homebanking, sem o abrir e voltar a guardar noutra aplicação "
    "(Excel, LibreOffice, Google Sheets), ou corrija o ficheiro e carregue-o de novo."
)


def _fail(problems: list[str]) -> ParseError:
    return ParseError(
        "O ficheiro não está de acordo com o formato do export do Bankinter e não foi importado:\n• "
        + "\n• ".join(problems)
        + f"\n{HINT}"
    )


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")  # BOM aceite; qualquer outra codificação é recusada
    except UnicodeDecodeError as e:
        raise _fail(["O ficheiro não está em UTF-8 (foi provavelmente guardado por outra aplicação)."]) from e


def _parse_date(s: str) -> date:
    return datetime.strptime(s.strip(), "%d-%m-%Y").date()


def _why_bad_amount(t: str) -> tuple[str, str]:
    """(tipo, explicação) do motivo por que `t` não está no formato do Bankinter (ex.: -889,50)."""
    if t == "":
        return "branco", "valor em branco"
    if re.fullmatch(r"-?\d{1,3}(,\d{3})+\.\d{1,2}", t):
        return "ponto_milhares", (
            "usa vírgula de milhares e ponto decimal (ex.: 37,778.46); "
            "o Bankinter usa vírgula decimal e não tem milhares (ex.: 37778,46)"
        )
    if re.fullmatch(r"-?\d+\.\d{1,2}", t):
        return (
            "ponto",
            "usa ponto como separador decimal (ex.: 889.50); o Bankinter usa vírgula (ex.: 889,50)",
        )
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+,\d{1,2}", t):
        return (
            "milhares",
            "tem ponto como separador de milhares (ex.: 1.234,56); o Bankinter não o usa (ex.: 1234,56)",
        )
    if re.fullmatch(r"-?\d+(,\d)?", t) or re.fullmatch(r"-?\d+,\d{3,}", t):
        return "casas", "não tem exatamente 2 casas decimais (ex.: 889,50)"
    return "naonum", "não é um valor numérico no formato do Bankinter (ex.: -889,50)"


def _rows(text: str, delimiter: str = ",") -> list[list[str]]:
    return list(csv.reader(io.StringIO(text), delimiter=delimiter))


def _find_header(rows: list[list[str]]) -> int | None:
    for i, r in enumerate(rows):
        if r and r[0].strip().casefold() == "data movimento":
            return i
    return None


def parse_rows(rows: list[list[str]]) -> ParsedStatement:
    """Validação estrita partilhada pelo CSV e pelo .xls: `rows` são as linhas da folha, em texto."""
    h = _find_header(rows)
    if h is None:
        raise _fail(["Não encontrei a linha de colunas «Data Movimento, Data Valor, Descrição, …»."])
    found = [c.strip() for c in rows[h]]
    while found and not found[-1]:
        found.pop()
    if [c.casefold() for c in found] != [c.casefold() for c in EXPECTED_HEADER]:
        raise _fail(
            [
                "As colunas não correspondem ao modelo do Bankinter.",
                "Esperado: " + ", ".join(EXPECTED_HEADER) + ".",
                "Encontrado: " + ", ".join(found) + ".",
            ]
        )
    idx = {name: i for i, name in enumerate(c.casefold() for c in EXPECTED_HEADER)}

    moeda = periodo_inicio = periodo_fim = None
    for r in rows[:h]:
        line = " ".join(r)
        if moeda is None and (m := _CURRENCY_RE.search(line)):
            moeda = m.group(1)
        if periodo_inicio is None and (m := _PERIOD_RE.search(line)):
            periodo_inicio, periodo_fim = _parse_date(m.group(1)), _parse_date(m.group(2))

    # Problemas agregados por tipo («N ocorrências; primeira na linha L, «exemplo»»): um ficheiro de um ano com
    # ponto decimal daria centenas de queixas iguais.
    agg: dict[str, dict] = {}

    def bad(key: str, texto: str, lineno: int, ex: str = "") -> None:
        a = agg.setdefault(key, {"n": 0, "linha": lineno, "ex": ex, "texto": texto})
        a["n"] += 1

    cells: list[tuple[date, date | None, str, str, str]] = []
    for lineno, r in enumerate(rows[h + 1 :], start=h + 2):
        first = r[0].strip() if r else ""
        if _DATE_LIKE_RE.match(first) and not _DATE_RE.match(first):
            bad(
                "data_fmt",
                "Data num formato inesperado (esperado dd-mm-aaaa, ex.: 05-10-2026)",
                lineno,
                first,
            )
            continue
        if not _DATE_RE.match(first):
            break  # fim dos dados (linha em branco ou rodapé)
        if len(r) <= idx["saldo"]:
            bad(
                "cols",
                f"Linha com colunas a menos (esperado {len(EXPECTED_HEADER)})",
                lineno,
                str(len(r)),
            )
            continue
        vd = r[idx["data valor"]].strip()
        if not _DATE_RE.match(vd):
            bad("data_valor", "Data Valor fora do formato dd-mm-aaaa", lineno, vd)
            continue
        mo = r[idx["moeda"]].strip()
        if mo != (moeda or "EUR"):
            bad("moeda", f"Moeda diferente de {moeda or 'EUR'}", lineno, mo)
        ok = True
        for col in ("montante", "saldo"):
            v = r[idx[col]].strip()
            if not _AMOUNT_RE.match(v):
                tipo, porque = _why_bad_amount(v)
                bad(f"{col}:{tipo}", f"{col.capitalize()} {porque}", lineno, v)
                ok = False
        try:
            dm, dvd = _parse_date(first), _parse_date(vd)
        except ValueError:
            bad("data_invalida", "Data inválida (dia ou mês inexistente)", lineno, f"{first} / {vd}")
            continue
        if ok:
            cells.append(
                (
                    dm,
                    dvd,
                    r[idx["descrição"]].strip(),
                    r[idx["montante"]].strip(),
                    r[idx["saldo"]].strip(),
                )
            )

    if periodo_inicio and periodo_fim:
        for dm, *_ in cells:
            if not (periodo_inicio <= dm <= periodo_fim):
                bad(
                    "periodo",
                    f"Datas fora do período indicado no cabeçalho ({periodo_inicio:%d-%m-%Y} a {periodo_fim:%d-%m-%Y})",
                    0,
                    f"{dm:%d-%m-%Y}",
                )
    if agg:
        raise _fail(
            [
                f"{a['texto']} — {a['n']} ocorrência(s)"
                + (f"; primeira na linha {a['linha']}" if a["linha"] else "")
                + (f", «{a['ex']}»" if a["ex"] else "")
                + "."
                for a in agg.values()
            ]
        )
    if not cells:
        raise _fail(["Nenhum movimento encontrado depois da linha de colunas."])

    raw = [
        (dm, dv, desc, Decimal(m.replace(",", ".")), Decimal(sd.replace(",", ".")))
        for dm, dv, desc, m, sd in cells
    ]

    return build_statement(raw, moeda, periodo_inicio, periodo_fim)


class BankinterCsvParser:
    bank_id = BANK_ID

    def can_parse(self, content: bytes) -> float:
        # Tolerante de propósito: se parece ser deste banco, o parse explica o que está errado.
        return 1.0 if b"data movimento" in content.lower() else 0.0

    def parse(self, content: bytes) -> ParsedStatement:
        text = _decode(content)
        rows = _rows(text)
        if _find_header(rows) is None and _find_header(_rows(text, ";")) is not None:
            raise _fail(["O ficheiro usa «;» como separador de campos; o export do Bankinter usa «,»."])
        return parse_rows(rows)
