"""Estrutura de um extrato bancário (.xls, .xlsx ou .csv) com os valores mascarados.

Serve para analisar o formato de um banco novo SEM expor dados pessoais. Corre na máquina do utilizador, que cola
a saída para análise; ninguém precisa de abrir o ficheiro real.

Máscara: letras -> «x», dígitos -> «9»; pontuação e separadores ficam (mostram o formato de datas e números, p.ex.
«99-99-9999», «9.999,99»). Só se mostram sem máscara palavras de um vocabulário genérico de extratos (data, valor,
montante, saldo, débito, …) nos nomes de colunas e nos rótulos do preâmbulo. Descrições, nomes, IBAN e valores
nunca aparecem. `--mostrar-rotulos` mostra TODOS os nomes de colunas e rótulos: use só depois de confirmar que a
linha do cabeçalho não tem dados pessoais.

Usado por `scripts/mask_statement.py` (linha de comandos) e pelo assistente «Adicionar conta» (outro banco).
"""

import csv
import io
import re
from collections import Counter


class UnsupportedFormat(ValueError):
    """Formato de ficheiro que não sabemos descrever (PDF, HTML, ...)."""


VOCAB = {
    "data",
    "datas",
    "movimento",
    "movimentos",
    "mov",
    "valor",
    "descrição",
    "descricao",
    "descritivo",
    "descrições",
    "transação",
    "transacção",
    "transacao",
    "operação",
    "operacao",
    "montante",
    "montantes",
    "saldo",
    "saldos",
    "contabilístico",
    "contabilistico",
    "disponível",
    "disponivel",
    "débito",
    "debito",
    "crédito",
    "credito",
    "moeda",
    "divisa",
    "referência",
    "referencia",
    "categoria",
    "tipo",
    "período",
    "periodo",
    "de",
    "a",
    "até",
    "ate",
    "no",
    "na",
    "do",
    "da",
    "dos",
    "das",
    "conta",
    "nº",
    "n",
    "número",
    "numero",
    "extrato",
    "extracto",
    "lançamento",
    "lancamento",
    "lancamentos",
    "taxa",
    "câmbio",
    "cambio",
    "date",
    "description",
    "amount",
    "balance",
    "debit",
    "credit",
    "currency",
    "reference",
    "booking",
    "value",
    "type",
    "account",
    "from",
    "to",
    "period",
    "statement",
    "transaction",
    "details",
    "detail",
    "narrative",
    "entry",
    "posting",
    "running",
    "available",
    "ledger",
    "iban",
    "nib",
}
CTYPE = {
    0: "vazio",
    1: "texto",
    2: "número",
    3: "data",
    4: "booleano",
    5: "erro",
    6: "vazio",
}


def mask(s: str) -> str:
    return re.sub(r"[^\W\d_]", "x", re.sub(r"\d", "9", s))


def shape(s: str) -> str:
    """Forma de um valor para estatística por coluna: decimais com o nº exato de casas, o resto colapsado."""
    s = mask(s.strip())
    s = re.sub(r"(?<=[.,])9+", lambda m: "D" * len(m.group()), s)  # casas decimais/milhares: contam
    s = re.sub(r"9+", "9+", s)
    s = re.sub(r"x+", "x+", s)
    return s.replace("D", "9")


def numstr(v) -> str:
    """Número sem artefactos de float (900.0 -> «900»): as casas decimais que sobram são as reais do ficheiro."""
    try:
        return format(float(v), ".10f").rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(v)


def words_ok(s: str) -> bool:
    ws = re.findall(r"[^\W\d_]+", s.casefold())
    return bool(ws) and not re.search(r"\d", s) and all(w in VOCAB for w in ws)


def label(s: str, show_all: bool) -> str:
    """Texto de cabeçalho/rótulo: sem máscara só se for vocabulário genérico (ou com --mostrar-rotulos)."""
    s = s.strip()
    return s if show_all or words_ok(s) else mask(s)


# célula = (tipo, valor, formato)
def rows_xls(content: bytes):
    import xlrd

    book = xlrd.open_workbook(file_contents=content, formatting_info=True)
    for sh in book.sheets():
        rows = []
        for r in range(sh.nrows):
            row = []
            for c in range(sh.ncols):
                cell = sh.cell(r, c)
                fmt = ""
                if cell.ctype in (2, 3):
                    fmt = book.format_map[book.xf_list[cell.xf_index].format_key].format_str
                row.append(
                    (
                        CTYPE[cell.ctype],
                        cell.value if cell.ctype in (1, 2, 3) else "",
                        fmt,
                    )
                )
            rows.append(row)
        yield sh.name, rows, f"células unidas: {len(sh.merged_cells)}"


def rows_xlsx(content: bytes):
    try:
        import openpyxl
    except ImportError:
        raise UnsupportedFormat("Para .xlsx falta a biblioteca openpyxl neste servidor.")
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    for ws in wb.worksheets:
        rows = []
        for r in ws.iter_rows():
            row = []
            for c in r:
                v = c.value
                if v is None or v == "":
                    row.append(("vazio", "", ""))
                elif isinstance(v, bool):
                    row.append(("booleano", v, ""))
                elif isinstance(v, (int, float)):
                    row.append(("número", v, c.number_format))
                elif hasattr(v, "year"):
                    row.append(("data", str(v), c.number_format))
                else:
                    row.append(("texto", str(v), ""))
            rows.append(row)
        yield ws.title, rows, f"células unidas: {len(ws.merged_cells.ranges)}"


def rows_csv(content: bytes):
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:5000]
    delim = max(",;\t|", key=sample.count)
    rows = [
        [("texto" if c.strip() else "vazio", c, "") for c in line]
        for line in csv.reader(io.StringIO(text), delimiter=delim)
    ]
    yield (
        "csv",
        rows,
        f"codificação: {enc}; separador: {delim!r}; fim de linha: {'CRLF' if chr(13) in sample else 'LF'}",
    )


def find_header(rows) -> int | None:
    """1.ª linha só com texto (≥3 células) seguida de uma linha com data/número ou com texto em forma de data/valor."""
    for i, row in enumerate(rows[:-1]):
        filled = [c for c in row if c[0] != "vazio"]
        if len(filled) >= 3 and all(c[0] == "texto" for c in filled):
            nxt = [c for c in rows[i + 1] if c[0] != "vazio"]
            if any(
                c[0] in ("data", "número") or re.fullmatch(r"[-+]?[\d.,/ -]+", str(c[1]).strip() or "x")
                for c in nxt
            ):
                return i
    return None


def show(cell, header: bool, show_all: bool) -> str:
    kind, v, fmt = cell
    if kind == "vazio":
        return "·"
    if kind == "texto":
        s = str(v).strip()
        if header:
            return f"texto:{label(s, show_all)}"
        if ":" in s and len(s.split(":")[0]) < 40:  # «Rótulo: valor» no preâmbulo
            k, _, rest = s.partition(":")
            return f"texto:{label(k, show_all)}:{mask(rest)}"
        return f"texto:{mask(s)}"
    extra = f"(fmt={fmt})" if fmt else ""
    return f"{kind}{extra}:{mask(numstr(v) if kind == 'número' else str(v))}"


def describe_bytes(content: bytes, show_all: bool = False) -> str:
    """Estrutura mascarada do extrato (texto). Levanta UnsupportedFormat se o formato não for suportado."""
    lines: list[str] = []

    def p(*a):
        lines.append(" ".join(str(x) for x in a))

    p(f"({len(content)} bytes)")
    head = content[:8]
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        kind, gen = ".xls", rows_xls
    elif head.startswith(b"PK\x03\x04"):
        kind, gen = ".xlsx", rows_xlsx
    elif head.startswith(b"%PDF"):
        raise UnsupportedFormat("PDF: não suportado. Peça ao banco o extrato em .xls, .xlsx ou .csv.")
    elif head.lstrip().startswith(b"<"):
        p(
            "início (mascarado):",
            mask(content[:300].decode("latin-1")).replace("\n", "¦"),
        )
        raise UnsupportedFormat("Parece HTML/XML guardado como extrato: não suportado.")
    else:
        kind, gen = "csv/texto", rows_csv
    p("formato detetado:", kind)
    for name, rows, note in gen(content):
        ncols = max((len(r) for r in rows), default=0)
        p(f"\n--- folha «{label(name, show_all)}»: {len(rows)} linhas × {ncols} colunas; {note}")
        hdr = find_header(rows)
        p("linha do cabeçalho (0-based):", hdr)
        if hdr is None:
            for i, r in enumerate(rows[:12]):
                p(f" [{i:>3}]", " | ".join(show(c, False, show_all) for c in r))
            continue
        for i in range(hdr + 1):
            p(f" [{i:>3}]", " | ".join(show(c, i == hdr, show_all) for c in rows[i]))
        data = rows[hdr + 1 :]
        p("\n primeiras 3 linhas de dados:")
        for i, r in enumerate(data[:3]):
            p(f" [{hdr + 1 + i:>3}]", " | ".join(show(c, False, show_all) for c in r))
        p(" últimas 3 linhas:")
        for i, r in enumerate(data[-3:], len(data) - 3):
            p(f" [{hdr + 1 + i:>3}]", " | ".join(show(c, False, show_all) for c in r))
        p("\n tipo, formato e forma por coluna (todas as linhas após o cabeçalho):")
        for c in range(ncols):
            cnt: Counter = Counter()
            for r in data:
                if c < len(r) and r[c][0] != "vazio":
                    cnt[
                        (
                            r[c][0],
                            r[c][2],
                            shape(numstr(r[c][1]) if r[c][0] == "número" else str(r[c][1])),
                        )
                    ] += 1
                else:
                    cnt[("vazio", "", "")] += 1
            name_c = label(str(rows[hdr][c][1]), show_all) if c < len(rows[hdr]) else "?"
            top = ", ".join(
                f"{k[0]}{'(fmt=' + k[1] + ')' if k[1] else ''} «{k[2]}» ×{n}" for k, n in cnt.most_common(4)
            )
            p(f"   col {c} «{name_c}»: {top}")
        p(
            f"\n linhas de dados: {len(data)}; linhas totalmente vazias no meio: {sum(1 for r in data if all(x[0] == 'vazio' for x in r))}"
        )
    return "\n".join(lines)
