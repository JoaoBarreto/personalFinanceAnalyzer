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
    return len(tok) >= 6 and sum(c.isdigit() for c in tok) >= 3 and any(c.isalpha() for c in tok)


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


def normalize_pattern(padrao: str) -> str:
    """Padrões de regra: maiúsculas, sem acentos, espaços colapsados (sem remoção de ruído)."""
    return re.sub(r"\s+", " ", unidecode(padrao).upper()).strip()


_STOP = {"DE", "DA", "DO", "DOS", "DAS", "LDA", "SA", "WWW", "COM", "PT", "LISBOA", "PORTO", "LOURES"}


def suggest_keyword(descricao_normalizada: str) -> str:
    """Keyword proposta para uma regra (PRD 3.6): 1.º token útil, p.ex. FNAC e não FNAC CHIADO LISBOA 12/03."""
    tokens = [re.sub(r"^\W+|\W+$", "", t) for t in descricao_normalizada.split()]
    tokens = [t for t in tokens if t and t not in _STOP]
    for t in tokens:
        if len(t) >= 4:
            return t
    return " ".join(tokens[:2]) or descricao_normalizada
