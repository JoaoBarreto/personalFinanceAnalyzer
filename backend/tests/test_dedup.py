from datetime import date
from decimal import Decimal as D

from app.parsers.banks.bankinter.csv_export import BankinterCsvParser
from app.services.dedup import Row, deduplicate

from .conftest import N_LINHAS, build_csv

d1, d2 = date(2026, 10, 1), date(2026, 10, 2)


def rows():
    s = BankinterCsvParser().parse(build_csv())
    return [Row(m.data_movimento, m.montante, m.saldo_apos) for m in s.movimentos]


def test_mesmo_ficheiro_duas_vezes_nao_insere_nada():
    r = rows()
    res = deduplicate(r, r)
    assert res.novos == [] and len(res.duplicados) == N_LINHAS and res.possiveis_duplicados == []


def test_primeira_importacao_insere_tudo():
    assert len(deduplicate(rows(), []).novos) == N_LINHAS


def test_periodo_sobreposto_so_insere_novas():
    r = rows()
    res = deduplicate(r, r[:5])
    assert res.duplicados == list(range(5)) and res.novos == list(range(5, N_LINHAS))


def test_compra_reembolso_compra_mesmo_dia():
    # -10 (saldo 90), +10 (saldo 100), -10 (saldo 90): a mesma chave aparece 2x e ambas contam.
    f = [Row(d1, D(-10), D(90)), Row(d1, D(10), D(100)), Row(d1, D(-10), D(90))]
    assert deduplicate(f, f).novos == []
    assert deduplicate(f, f[:2]).novos == [2]  # só a 3ª linha falta na BD


def test_multiset_sem_saldo_conta_ocorrencias():
    f = [Row(d1, D(-5), None)] * 3
    res = deduplicate(f, [Row(d1, D(-5), None)] * 2)
    assert len(res.duplicados) == 2 and len(res.novos) == 1


def test_um_lado_sem_saldo_cai_na_chave_base():
    # PDF sem saldo importado antes do Excel (e vice-versa): não duplica.
    assert deduplicate([Row(d1, D(-7), D(50))], [Row(d1, D(-7), None)]).duplicados == [0]
    assert deduplicate([Row(d1, D(-7), None)], [Row(d1, D(-7), D(50))]).duplicados == [0]


def test_saldo_diferente_e_ambiguo():
    res = deduplicate([Row(d1, D(-7), D(50))], [Row(d1, D(-7), D(99))])
    assert res.possiveis_duplicados == [0] and res.novos == [] and res.duplicados == []


def test_datas_diferentes_nao_colidem():
    res = deduplicate([Row(d2, D(-7), D(50))], [Row(d1, D(-7), D(50))])
    assert res.novos == [0]
