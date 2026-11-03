from .banks.bankinter.csv_export import BankinterCsvParser
from .base import StatementParser

PARSERS: dict[str, StatementParser] = {
    "bankinter_csv": BankinterCsvParser(),
}


def get_parser(parser_id: str) -> StatementParser | None:
    return PARSERS.get(parser_id)
