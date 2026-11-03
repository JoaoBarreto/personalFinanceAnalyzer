import pytest

from app.services.normalizer import normalize


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("COMPRA 4532 FNAC CHIADO LISBOA 12/03 REF 88231", "FNAC CHIADO LISBOA"),  # exemplo do PRD
        ("COMPRA 0000000.38 SUPERMERCADO X", "SUPERMERCADO X"),
        ("COMPRA 0000000 WWW.LOJA.COM B85YY73T4", "WWW.LOJA.COM"),
        ("COMPRA 0000000.45 BK27052 MERCEARIA LISBOA", "MERCEARIA LISBOA"),
        ("COMPRA 0000000.56 BOMBA E0772", "BOMBA"),
        ("COMPRA 0000000.49 A9", "A9"),  # portagem: código curto é informação
        ("COMPRA 0000000.28 03-TRANSACOES XYZ", "03-TRANSACOES XYZ"),  # 2 dígitos não é referência
        ("DD SERVICO LUZ-00000000000", "SERVICO LUZ"),
        ("TRF A CREDITO SEPA+ - EMPRESA X", "EMPRESA X"),
        ("Trf Imediata p/ Maria Silva", "MARIA SILVA"),
        ("IMPOSTO DO SELO S/ COMISSÃO S/ TRF P/ In", "IMPOSTO DO SELO S/ COMISSAO S/ TRF P/ IN"),
        ("MB WAY 12/03 14:35 CAFE CENTRAL", "CAFE CENTRAL"),
        ("  compra   1234   padaria   ", "PADARIA"),
    ],
)
def test_normalize(entrada, esperado):
    assert normalize(entrada) == esperado


def test_nunca_devolve_vazio():
    assert normalize("COMPRA 1234") != ""
    assert normalize("12345") == "12345"


def test_idempotente():
    for d in ("COMPRA 4532 FNAC CHIADO LISBOA 12/03 REF 88231", "TRF A CREDITO SEPA+ - EMPRESA X"):
        assert normalize(normalize(d)) == normalize(d)
