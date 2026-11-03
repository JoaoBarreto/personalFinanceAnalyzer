"""Parser do Bankinter: despacha pelo CONTEÚDO (.xls original ou CSV), sempre com validação estrita."""

from ...base import ParsedStatement
from .csv_export import BankinterCsvParser, _fail
from .xls_export import is_xls, parse_xls

_csv = BankinterCsvParser()


class BankinterParser:
    bank_id = "bankinter"

    def can_parse(self, content: bytes) -> float:
        return 1.0 if is_xls(content) else _csv.can_parse(content)

    def parse(self, content: bytes) -> ParsedStatement:
        if is_xls(content):
            return parse_xls(content)
        if content.startswith(b"PK"):
            raise _fail(["Ficheiros .xlsx não são aceites; carregue o .xls original do homebanking."])
        return _csv.parse(content)
