"""Propõe um Template a partir de um extrato carregado e VERIFICA a proposta antes de a mostrar.

Nada se grava aqui. A proposta só é devolvida se (1) o parser genérico, com esse modelo, aceitar o ficheiro e (2) a
cadeia de saldos reconciliar em todas as linhas: é isso que escolhe, entre as colunas numéricas, qual é o montante e
qual é o saldo. Ambiguidades que não se resolvem (dd/mm contra mm/dd; várias colunas que reconciliam) voltam como
PERGUNTAS ao utilizador, nunca se escolhe por ele. Um erro de escala uniforme (ex.: «-889.50» lido como -88950) não é
apanhado pela cadeia: por isso o ecrã de confirmação mostra o texto original ao lado do valor lido.
"""

from __future__ import annotations

import csv
import io
import re
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from ..base import ParseError
from .parser import DATE_SHAPE, GenericParser, amount_regex, parse_date_text, to_money
from .reader import Cell, read_grid, sniff
from .template import FORMATOS_DATA, MILHARES, Template

_NUMERIC_TEXT = re.compile(r"^-?[\d.,   ]+$")
_DESC_HINTS = (
    "descri",
    "detalhe",
    "narrativ",
    "description",
    "details",
    "movimento",
    "referência",
    "referencia",
)
_VALOR_HINTS = ("valor", "value")
_MOV_HINTS = ("mov", "oper", "lanç", "lanc", "contab", "booking", "date", "data")
AMOSTRA = 8


def _no(motivo: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "modelo": None, "perguntas": [], "amostra": [], "motivo": motivo, **extra}


def _csv_settings(content: bytes) -> tuple[str, str] | None:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        return None
    lines = [ln for ln in text.splitlines() if ln.strip()][:80]
    best, best_score = None, 0
    for sep in (",", ";", "\t", "|"):
        counts = [len(r) for r in csv.reader(io.StringIO("\n".join(lines)), delimiter=sep)]
        modal = max(set(counts), key=counts.count)
        score = counts.count(modal) if modal >= 3 else 0
        if score > best_score:
            best, best_score = sep, score
    return None if best is None else (enc, best)


def _date_like(c: Cell) -> bool:
    return c[0] == "data" or (c[0] == "texto" and bool(DATE_SHAPE.match(c[1])))


def _find_header(grid: list[list[Cell]]) -> int | None:
    for i, row in enumerate(grid[:-1]):
        filled = [c for c in row if c[0] != "vazio"]
        if (
            len(filled) >= 3
            and all(c[0] == "texto" for c in filled)
            and any(_date_like(c) for c in grid[i + 1])
        ):
            return i
    return None


def _cell(row: list[Cell], i: int) -> Cell:
    return row[i] if i < len(row) else ("vazio", "")


def _show(c: Cell) -> str:
    k, v = c
    if k == "vazio":
        return ""
    if k == "data":
        return v.strftime("%Y-%m-%d") if hasattr(v, "strftime") else str(v)
    if k == "num":
        return format(v, "f") if isinstance(v, Decimal) else repr(v)
    return str(v)


def detect(content: bytes, respostas: dict[str, Any] | None = None) -> dict[str, Any]:
    respostas = respostas or {}
    formato = sniff(content)
    if formato in ("pdf", "html"):
        return _no("Este tipo de ficheiro não é suportado: exporte o extrato em .xls, .xlsx ou .csv.")
    enc = sep = None
    if formato == "csv":
        cfg = _csv_settings(content)
        if cfg is None:
            return _no("Não consegui perceber a codificação do ficheiro de texto.")
        enc, sep = cfg
    try:
        grid = read_grid(content, formato, enc, sep)
    except ParseError as e:
        return _no(str(e))

    h = _find_header(grid)
    if h is None:
        return _no(
            "Não encontrei a linha de colunas (uma linha só com títulos, seguida de movimentos com data)."
        )
    header_cells = grid[h]
    names = [str(v).strip() if k != "vazio" else "" for k, v in header_cells]
    while names and not names[-1]:
        names.pop()
    region = []
    for row in grid[h + 1 :]:
        if not any(_date_like(c) for c in row):
            break
        region.append(row)
    if len(region) < 2:
        return _no("Poucos movimentos para validar o formato (preciso de pelo menos 2 linhas).")
    ncol = len(names)

    def column(j: int) -> list[Cell]:
        return [_cell(r, j) for r in region]

    # --- colunas de data (todas as linhas da região têm de ser datas) ---
    date_cols = [j for j in range(ncol) if all(_date_like(c) for c in column(j))]
    if not date_cols:
        return _no("Não encontrei uma coluna em que todas as linhas sejam datas.")

    def hint_rank(j: int, hints: tuple[str, ...]) -> int:
        n = names[j].casefold()
        return 0 if any(h_ in n for h_ in hints) else 1

    c_data = min(date_cols, key=lambda j: (hint_rank(j, _VALOR_HINTS) == 0, hint_rank(j, _MOV_HINTS), j))
    others = [j for j in date_cols if j != c_data]
    c_valor = min(others, key=lambda j: (hint_rank(j, _VALOR_HINTS), j)) if others else None

    # --- formato da data ---
    native = all(c[0] == "data" for c in column(c_data))
    perguntas: list[dict[str, Any]] = []
    formato_data = "dd-mm-aaaa"
    if not native:
        textos = [c[1] for c in column(c_data)] + (
            [c[1] for c in column(c_valor)] if c_valor is not None else []
        )
        if any(not isinstance(t, str) for t in textos):
            return _no("A coluna de datas mistura datas do Excel com texto.")
        cand = []
        for f in FORMATOS_DATA:
            try:
                if all(parse_date_text(t, f) is not None for t in textos):
                    cand.append(f)
            except ValueError:
                continue
        if not cand:
            return _no(
                "As datas não estão num formato suportado (dd-mm-aaaa, dd/mm/aaaa, dd.mm.aaaa, aaaa-mm-dd…)."
            )
        if len(cand) > 1:
            esc = respostas.get("formato_data")
            if esc in cand:
                cand = [esc]
            else:
                perguntas.append(
                    {
                        "id": "formato_data",
                        "texto": "Os dias e os meses são ambíguos neste extrato. Qual é a ordem das datas?",
                        "opcoes": [{"valor": f, "rotulo": f.replace("aaaa", "ano")} for f in cand],
                    }
                )
        formato_data = cand[0]

    # --- colunas numéricas ---
    def is_num_col(j: int) -> bool:
        cells = [c for c in column(j) if c[0] != "vazio"]
        if not cells:
            return False
        if all(c[0] == "num" for c in cells):
            return True
        return all(c[0] == "texto" and _NUMERIC_TEXT.match(c[1]) and re.search(r"\d", c[1]) for c in cells)

    num_cols = [j for j in range(ncol) if j not in date_cols and is_num_col(j)]
    if len(num_cols) < 2:
        return _no("Não encontrei pelo menos duas colunas numéricas (montante e saldo).")
    if len(num_cols) > 8:
        return _no("Demasiadas colunas numéricas para identificar o montante e o saldo.")

    # --- decimal e milhares, deduzidos dos textos com a regra «exatamente 2 casas» ---
    strings = [c[1] for j in num_cols for c in column(j) if c[0] == "texto"]
    decimal, milhares = ",", "nenhum"
    if strings:
        viable = {
            (d, m)
            for d in (",", ".")
            for m in MILHARES
            if (d, m)
            in {
                (",", "nenhum"),
                (",", "ponto"),
                (",", "espaco"),
                (".", "nenhum"),
                (".", "virgula"),
                (".", "espaco"),
            }
            and all(amount_regex(d, m).match(s) for s in strings)
        }
        if not viable:
            return _no("Os valores não têm todos exatamente 2 casas decimais com separadores consistentes.")
        decimals = sorted({d for d, _ in viable})
        if len(decimals) > 1:
            return _no("Não consegui perceber o separador decimal.")
        decimal = decimals[0]
        milhares = min((m for d, m in viable if d == decimal), key=MILHARES.index)

    probe = _probe(decimal, milhares)

    def values(j: int) -> list[Decimal | None] | None:
        out: list[Decimal | None] = []
        for c in column(j):
            if c[0] == "vazio":
                out.append(None)
                continue
            try:
                out.append(to_money(c, probe))
            except ValueError:
                return None
        return out

    vals = {j: values(j) for j in num_cols}
    vals = {j: v for j, v in vals.items() if v is not None}

    def chain(amount: list[Decimal], saldo: list[Decimal]) -> bool:
        asc = all(saldo[i - 1] + amount[i] == saldo[i] for i in range(1, len(saldo)))
        desc = all(saldo[i] + amount[i - 1] == saldo[i - 1] for i in range(1, len(saldo)))
        return asc or desc

    full = [j for j, v in vals.items() if all(x is not None for x in v)]
    opcoes: list[dict[str, Any]] = []
    for m in full:
        for s in full:
            if m != s and chain(vals[m], vals[s]):  # type: ignore[arg-type]
                opcoes.append({"tipo": "montante", "montante": m, "saldo": s})
    if not opcoes:
        for d in num_cols:
            for c_ in num_cols:
                for s in full:
                    if len({d, c_, s}) < 3 or d not in vals or c_ not in vals:
                        continue
                    dv, cv, sv = vals[d], vals[c_], vals[s]
                    if any((x or 0) != 0 and (y or 0) != 0 for x, y in zip(dv, cv, strict=True)):
                        continue
                    for sinal in ("positivo", "negativo"):
                        amt = [
                            (cv[i] or Decimal(0))
                            + (-(dv[i] or Decimal(0)) if sinal == "positivo" else (dv[i] or Decimal(0)))
                            for i in range(len(sv))
                        ]
                        if all(a != 0 for a in amt) and chain(amt, sv):  # type: ignore[arg-type]
                            opcoes.append(
                                {"tipo": "debcred", "debito": d, "credito": c_, "saldo": s, "sinal": sinal}
                            )
    if not opcoes:
        return _no(
            "Não consegui ligar o montante ao saldo (a cadeia «saldo anterior + montante = saldo» não fecha). "
            "O extrato precisa de uma coluna de saldo por movimento."
        )
    if len(opcoes) > 1:
        esc = respostas.get("colunas")
        if isinstance(esc, int) and 0 <= esc < len(opcoes):
            opcoes = [opcoes[esc]]
        else:
            perguntas.append(
                {
                    "id": "colunas",
                    "texto": "Mais do que uma combinação de colunas fecha as contas. Qual é a correta?",
                    "opcoes": [{"valor": i, "rotulo": _rotulo(o, names)} for i, o in enumerate(opcoes)],
                }
            )
    escolha = opcoes[0]

    # --- descrição: a coluna de texto com nome de «descrição», ou a de texto mais longo ---
    usados = {
        c_data,
        c_valor,
        *(v for k, v in escolha.items() if k in ("montante", "debito", "credito", "saldo")),
    }
    texto_cols = [j for j in range(ncol) if j not in usados and j not in date_cols and j not in num_cols]
    if not texto_cols:
        return _no("Não encontrei uma coluna de descrição.")

    def desc_score(j: int):
        comp = sum(len(str(c[1])) for c in column(j)) / len(region)
        return (hint_rank(j, _DESC_HINTS), -comp)

    c_desc = min(texto_cols, key=desc_score)

    modelo = {
        "formato": formato,
        "codificacao": enc,
        "separador": sep,
        "cabecalho": names,
        "data": names[c_data],
        "formato_data": formato_data,
        "celulas_data_nativas": native,
        "data_valor": names[c_valor] if c_valor is not None else None,
        "descricao": [names[c_desc]],
        "saldo": names[escolha["saldo"]],
        "decimal": decimal,
        "milhares": milhares,
    }
    if escolha["tipo"] == "montante":
        modelo["montante"] = names[escolha["montante"]]
    else:
        modelo.update(
            debito=names[escolha["debito"]], credito=names[escolha["credito"]], sinal_debito=escolha["sinal"]
        )
    if perguntas:
        return {
            "ok": False,
            "modelo": None,
            "perguntas": perguntas,
            "amostra": [],
            "motivo": None,
            "colunas": names,
        }
    res = verify(content, modelo)
    res["colunas"] = names
    return res


def _probe(decimal: str, milhares: str) -> Template:
    return Template(
        formato="csv", codificacao="utf-8", separador=",", cabecalho=["a", "b", "c", "d"], data="a",
        formato_data="dd-mm-aaaa", descricao=["b"], montante="c", saldo="d", decimal=decimal, milhares=milhares,
    )  # fmt: skip


def _rotulo(o: dict[str, Any], names: list[str]) -> str:
    if o["tipo"] == "montante":
        return f"Montante = «{names[o['montante']]}», saldo = «{names[o['saldo']]}»"
    return (
        f"Débito = «{names[o['debito']]}», crédito = «{names[o['credito']]}», saldo = «{names[o['saldo']]}»"
    )


def verify(content: bytes, modelo: dict[str, Any]) -> dict[str, Any]:
    """Valida o modelo (também o editado pelo utilizador) contra o ficheiro e devolve uma amostra para confirmar."""
    try:
        t = Template.model_validate(modelo)
    except ValidationError as e:
        return _no(
            "Modelo inválido: " + "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
        )
    try:
        st = GenericParser(t).parse(content)
    except ParseError as e:
        return _no(str(e))
    if not st.reconciliado:
        return _no(
            f"As contas não fecham em {len(st.quebras)} linha(s): o modelo não corresponde ao ficheiro."
        )
    grid = read_grid(content, t.formato, t.codificacao, t.separador)
    want = [c.strip().casefold() for c in t.cabecalho]
    hdr = next(
        i
        for i, r in enumerate(grid)
        if [str(v).strip().casefold() if k != "vazio" else "" for k, v in r][: len(want)] == want
    )
    idx = {n: i for i, n in enumerate(want)}
    cols = [c for c in (t.data, t.data_valor, *t.descricao, t.montante, t.debito, t.credito, t.saldo) if c]
    file_order = st.movimentos if st.ordem_ficheiro == "asc" else list(reversed(st.movimentos))
    amostra = []
    for k in range(min(AMOSTRA, len(file_order))):
        row = grid[hdr + 1 + k]
        m = file_order[k]
        amostra.append(
            {
                "bruto": {c: _show(_cell(row, idx[c.strip().casefold()])) for c in cols},
                "lido": {
                    "data": m.data_movimento.isoformat(),
                    "descricao": m.descricao_original,
                    "montante": str(m.montante),
                    "saldo": str(m.saldo_apos),
                },
            }
        )
    resumo = {
        "movimentos": len(st.movimentos),
        "periodo": [st.periodo_inicio.isoformat(), st.periodo_fim.isoformat()],
        "ordem": st.ordem_ficheiro,
        "saldo_inicial": str(st.saldo_inicial),
        "saldo_final": str(st.saldo_final),
    }
    return {
        "ok": True,
        "modelo": t.model_dump(mode="json"),
        "perguntas": [],
        "amostra": amostra,
        "resumo": resumo,
        "motivo": None,
    }
