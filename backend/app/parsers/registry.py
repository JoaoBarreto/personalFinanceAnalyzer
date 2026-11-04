from .banks.bankinter.parser import BankinterParser
from .base import StatementParser

_bankinter = BankinterParser()
PARSERS: dict[str, StatementParser] = {
    "bankinter": _bankinter,
    "bankinter_csv": _bankinter,  # nome antigo das contas já criadas; mesmo parser (.xls ou CSV, por conteúdo)
}


def get_parser(parser_id: str) -> StatementParser | None:
    return PARSERS.get(parser_id)


# Valor de parser_id de uma conta cujo banco ainda não tem parser: pode ser criada, mas não importa extratos.
PENDING = "pendente"

# Bancos com parser, para o assistente «Adicionar conta». Um banco novo = pasta em banks/ + entrada aqui e em PARSERS.
BANKS = [
    {"parser_id": "bankinter", "banco": "Bankinter", "formatos": [".xls", ".csv"]},
]
