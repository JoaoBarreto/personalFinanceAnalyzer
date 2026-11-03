from .banks.bankinter.parser import BankinterParser
from .base import StatementParser

_bankinter = BankinterParser()
PARSERS: dict[str, StatementParser] = {
    "bankinter": _bankinter,
    "bankinter_csv": _bankinter,  # nome antigo das contas já criadas; mesmo parser (.xls ou CSV, por conteúdo)
}


def get_parser(parser_id: str) -> StatementParser | None:
    return PARSERS.get(parser_id)
