"""Normalização de descrições (PRD 3.4). Função pura; a descrição original é sempre preservada."""

import re

from unidecode import unidecode

_DATE = re.compile(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b")
_TIME = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")
_REF = re.compile(r"\bREF\.?\s*\S+")
# Prefixos de operação, removidos do início (repetidamente)
_PREFIX = re.compile(
    r"^(?:TRF\.?\s+A\s+CREDITO\s+SEPA\+|TRF\.?\s+IMEDIATA\s+P/|TRF\.?\s+P/|"
    r"COMPRA|PAGAMENTO|PAG\.?|DD|MB\s*WAY|TRF\.?)(?=[\s\-:]|$)[\s\-:]*"
)
_TRAILING_REF = re.compile(r"-\d{6,}\b")  # ex.: SERVICO LUZ-00000000000
_NUMERIC = re.compile(r"^\d+(?:[.,]\d+)*$")  # nº de cartão/terminal, ex.: 4532, 0000000.30
_CODE = re.compile(r"^[A-Z]{1,3}\d{3,}$")  # códigos de terminal, ex.: BK27052, E0772


def _is_noise(tok: str) -> bool:
    if _NUMERIC.match(tok) or _CODE.match(tok):
        return True
    # referências alfanuméricas longas, ex.: B85YY73T4
    return len(tok) >= 6 and sum(c.isdigit() for c in tok) >= 2 and any(c.isalpha() for c in tok)


def normalize(descricao: str) -> str:
    s = unidecode(descricao).upper()
    s = _TIME.sub(" ", _DATE.sub(" ", s))
    s = _TRAILING_REF.sub(" ", _REF.sub(" ", s))
    s = re.sub(r"\s+", " ", s).strip()
    prev = None
    while prev != s:  # prefixos encadeados
        prev, s = s, _PREFIX.sub("", s).strip()
    tokens = [t for t in s.split(" ") if t and not _is_noise(t)]
    out = " ".join(tokens).strip(" -,:;.")
    return out or re.sub(r"\s+", " ", unidecode(descricao).upper()).strip()
