from .banks.bankinter.parser import BankinterParser
from .base import StatementParser

_bankinter = BankinterParser()
PARSERS: dict[str, StatementParser] = {
    "bankinter": _bankinter,
    "bankinter_csv": _bankinter,  # nome antigo das contas já criadas; mesmo parser (.xls ou CSV, por conteúdo)
}


GENERIC = "generico"  # parser guiado por um modelo guardado na conta (config_importacao)


def get_parser(parser_id: str, config: dict | None = None) -> StatementParser | None:
    """Parser da conta. O genérico precisa do modelo da conta; se este for inválido não há parser."""
    if parser_id == GENERIC:
        from pydantic import ValidationError

        from .generic.parser import GenericParser
        from .generic.template import Template

        try:
            return GenericParser(Template.model_validate(config or {}))
        except ValidationError:
            return None
    return PARSERS.get(parser_id)


# Valor de parser_id de uma conta cujo banco ainda não tem parser: pode ser criada, mas não importa extratos.
PENDING = "pendente"

# Bancos com parser, para o assistente «Adicionar conta». Um banco novo = pasta em banks/ + entrada aqui e em PARSERS.
BANKS = [
    {"parser_id": "bankinter", "banco": "Bankinter", "formatos": [".xls", ".csv"]},
]
