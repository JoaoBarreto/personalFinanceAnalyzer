"""Modelo (template) de um extrato, guardado em `contas.config_importacao`.

É validado contra valores FIXOS (nunca uma regex nem um formato de data vindos do cliente) e referencia as colunas
pelo NOME, não pela posição: um ficheiro com colunas trocadas ou renomeadas é recusado pelo parser.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

FORMATOS_DATA = ("dd-mm-aaaa", "dd/mm/aaaa", "dd.mm.aaaa", "aaaa-mm-dd", "aaaa/mm/dd", "mm/dd/aaaa")
MILHARES = ("nenhum", "ponto", "espaco", "virgula")
_DECIMAL_MILHARES = {",": {"nenhum", "ponto", "espaco"}, ".": {"nenhum", "virgula", "espaco"}}


class Template(BaseModel):
    model_config = ConfigDict(extra="forbid")

    versao: Literal[1] = 1
    formato: Literal["xls", "xlsx", "csv"]
    codificacao: Literal["utf-8", "utf-8-sig", "cp1252"] | None = None  # só csv
    separador: Literal[",", ";", "\t", "|"] | None = None  # só csv
    cabecalho: list[str] = Field(min_length=3, max_length=60)  # nomes exatos das colunas (linha de cabeçalho)
    data: str  # data do movimento
    formato_data: Literal["dd-mm-aaaa", "dd/mm/aaaa", "dd.mm.aaaa", "aaaa-mm-dd", "aaaa/mm/dd", "mm/dd/aaaa"]
    celulas_data_nativas: bool = False  # xls/xlsx: a coluna de data tem células de data do Excel
    data_valor: str | None = None
    descricao: list[str] = Field(min_length=1, max_length=4)
    montante: str | None = None  # um só montante com sinal...
    debito: str | None = None  # ...ou colunas de débito e crédito
    credito: str | None = None
    sinal_debito: Literal["positivo", "negativo"] = "positivo"  # como vem o valor na coluna de débito
    saldo: str  # obrigatório: a cadeia de saldos é a rede de segurança da importação
    decimal: Literal[",", "."]
    milhares: Literal["nenhum", "ponto", "espaco", "virgula"] = "nenhum"
    moeda: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def _coerente(self):
        if self.formato == "csv":
            if self.codificacao is None or self.separador is None:
                raise ValueError("csv exige codificacao e separador")
        elif self.codificacao is not None or self.separador is not None:
            raise ValueError("codificacao/separador só se aplicam a csv")
        if self.celulas_data_nativas and self.formato == "csv":
            raise ValueError("células de data nativas não existem em csv")
        if (self.montante is None) == (self.debito is None and self.credito is None):
            raise ValueError("indique `montante` OU `debito` e `credito`")
        if self.montante is None and (self.debito is None or self.credito is None):
            raise ValueError("débito e crédito têm de vir os dois")
        if self.milhares not in _DECIMAL_MILHARES[self.decimal]:
            raise ValueError(
                f"separador de milhares {self.milhares!r} incompatível com decimal {self.decimal!r}"
            )
        norm = [c.strip().casefold() for c in self.cabecalho]
        refs = [self.data, self.saldo, *self.descricao]
        refs += [x for x in (self.data_valor, self.montante, self.debito, self.credito) if x]
        for r in refs:
            n = r.strip().casefold()
            if norm.count(n) != 1:
                raise ValueError(f"a coluna {r!r} tem de existir uma vez (e só uma) no cabeçalho")
        distintas = [r.strip().casefold() for r in refs]
        if len(set(distintas)) != len(distintas):
            raise ValueError("a mesma coluna não pode ter dois papéis")
        return self
