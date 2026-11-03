from decimal import Decimal as D

from app.services.categorizer import RuleData, best_rule, rule_matches
from app.services.normalizer import normalize_pattern, suggest_keyword


def R(id, padrao, tipo="contem", cat=1, **kw):
    return RuleData(id, padrao, tipo, cat, **kw)


def test_tipos_de_match():
    d = "FNAC CHIADO LISBOA"
    assert rule_matches(R(1, "CHIADO"), d, D(-5), 1)
    assert rule_matches(R(1, "FNAC", "comeca_por"), d, D(-5), 1)
    assert not rule_matches(R(1, "CHIADO", "comeca_por"), d, D(-5), 1)
    assert rule_matches(R(1, d, "igual"), d, D(-5), 1) and not rule_matches(
        R(1, "FNAC", "igual"), d, D(-5), 1
    )
    assert rule_matches(R(1, r"^FNAC\s.*LISBOA$", "regex"), d, D(-5), 1)
    assert not rule_matches(R(1, "(", "regex"), d, D(-5), 1)  # regex inválida nunca rebenta


def test_direcao_montante_e_conta():
    d = "LOJA"
    assert rule_matches(R(1, "LOJA", direcao="debito"), d, D(-1), 1)
    assert not rule_matches(R(1, "LOJA", direcao="debito"), d, D(1), 1)
    assert rule_matches(R(1, "LOJA", direcao="credito"), d, D(1), 1)
    assert not rule_matches(R(1, "LOJA", direcao="credito"), d, D(-1), 1)
    r = R(1, "LOJA", montante_min=D(10), montante_max=D(20))  # sobre |montante|
    assert (
        rule_matches(r, d, D(-15), 1)
        and not rule_matches(r, d, D("-9.99"), 1)
        and not rule_matches(r, d, D("-20.01"), 1)
    )
    assert rule_matches(R(1, "LOJA", conta_id=2), d, D(-1), 2) and not rule_matches(
        R(1, "LOJA", conta_id=2), d, D(-1), 1
    )


def test_desempate_prioridade_tipo_padrao_antiguidade():
    d = "CONTINENTE MODELO"
    amount = D(-5)
    # 1) prioridade
    assert (
        best_rule([R(1, "CONTINENTE", prioridade=100), R(2, "CONTINENTE", prioridade=200)], d, amount, 1).id
        == 2
    )
    # 2) tipo mais específico (igual > comeca_por > contem)
    rs = [R(1, d, "contem"), R(2, d, "comeca_por"), R(3, d, "igual")]
    assert best_rule(rs, d, amount, 1).id == 3
    assert best_rule(rs[:2], d, amount, 1).id == 2
    # 3) padrão mais longo
    assert best_rule([R(1, "CONT"), R(2, "CONTINENTE")], d, amount, 1).id == 2
    # 4) regra mais antiga
    assert best_rule([R(5, "CONT"), R(3, "CONT")], d, amount, 1).id == 3
    assert best_rule([R(1, "XYZ")], d, amount, 1) is None


def test_normalize_pattern_mantem_regex_intacta_nao_aplicavel():
    assert normalize_pattern("  Pingo  Doce ") == "PINGO DOCE"
    assert normalize_pattern("Café") == "CAFE"


def test_suggest_keyword():
    assert suggest_keyword("FNAC CHIADO LISBOA") == "FNAC"  # exemplo do PRD
    assert suggest_keyword("[GROCERY STORE] BOM DIA") == "GROCERY"
    assert suggest_keyword("WWW.LOJA.COM") == "WWW.LOJA.COM"
    assert suggest_keyword("A9") == "A9"
    assert suggest_keyword("DE LDA") == "DE LDA"
