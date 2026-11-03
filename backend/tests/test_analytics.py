from decimal import Decimal as D

from sqlalchemy import select

from app.models import Categoria

from .test_categorization_api import cat_id, import_all, txs

RECEITAS = D("3280.91")  # 900,00 + 2380,91 (constantes escritas à mão)
DESPESAS = D("872.99")  # 2,25 + 668,14 + 72,82 + 69,53 + 0,50 + 59,75


def get(api, path, **params):
    r = api.get(f"/api/analytics/{path}", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_summary_totais_batem_com_soma_manual(api, db):
    import_all(api)
    s = get(api, "summary", data_de="2026-10-01", data_ate="2026-10-31")
    assert (s["despesas"], s["receitas"], s["poupanca"]) == ("872.99", "3280.91", "2407.92")
    assert s["taxa_poupanca_pct"] == str(((RECEITAS - DESPESAS) / RECEITAS * 100).quantize(D("0.01")))
    assert s["n_por_categorizar"] == 8


def test_periodo_por_omissao_e_o_mes_do_ultimo_movimento(api, db):
    import_all(api)
    s = get(api, "summary")
    assert s["periodo"] == {"data_de": "2026-10-01", "data_ate": "2026-10-31"} and s["despesas"] == "872.99"


def test_transferencias_ficam_fora_dos_totais(api, db):
    import_all(api)
    tid = txs(api, q="EMPRESA")["items"][0]["id"]
    api.patch(f"/api/transactions/{tid}", json={"categoria_id": cat_id(db, "Transferências entre contas")})
    s = get(api, "summary", data_de="2026-10-01", data_ate="2026-10-31")
    assert s["receitas"] == "2380.91"
    com = get(api, "summary", data_de="2026-10-01", data_ate="2026-10-31", incluir_transferencias=True)
    assert com["receitas"] == "3280.91"


def test_by_category(api, db):
    import_all(api)
    sup = cat_id(db, "Supermercado")
    tid = txs(api, q="SUPERMERCADO")["items"][0]["id"]
    api.patch(f"/api/transactions/{tid}", json={"categoria_id": sup})
    j = get(api, "by-category", data_de="2026-10-01", data_ate="2026-10-31")
    assert j["total_despesas"] == "872.99"
    top = j["itens"][0]
    assert top["nome"] == "Por categorizar" and top["total"] == "813.24"  # 872,99 − 59,75
    s = next(i for i in j["itens"] if i["nome"] == "Supermercado")
    assert s["total"] == "59.75" and s["n"] == 1
    assert abs(sum(D(i["percentagem"]) for i in j["itens"]) - 100) <= D("0.02")  # arredondamentos
    pai = get(api, "by-category", data_de="2026-10-01", data_ate="2026-10-31", nivel="pai")
    alim = next(i for i in pai["itens"] if i["nome"] == "Alimentação")
    assert alim["total"] == "59.75"  # o filho sobe ao pai


def test_monthly_inclui_meses_vazios(api, db):
    import_all(api)
    import_all(api, [("05-12-2026", "05-12-2026", "COMPRA 0000000.99 LOJA", D("-10.00"))])
    j = get(api, "monthly", data_de="2026-10-01", data_ate="2026-12-31")
    m = j["periodos"]
    assert j["granularidade"] == "mes" and [x["periodo"] for x in m] == ["2026-10", "2026-11", "2026-12"]
    assert m[0]["despesas"] == "872.99"
    assert m[1]["despesas"] == m[1]["receitas"] == m[1]["poupanca"] == "0.00"
    assert m[2]["despesas"] == "10.00" and m[2]["poupanca"] == "-10.00"
    assert (
        m[0]["saldo_fim"] == "3407.92" and m[1]["saldo_fim"] == "3407.92"
    )  # sem movimentos: o saldo mantém-se


def test_comparacoes_com_mes_anterior_e_medias(api, db):
    import_all(api)
    import_all(api, [("05-11-2026", "05-11-2026", "COMPRA 0000000.99 LOJA", D("-436.50"))])
    s = get(api, "summary", data_de="2026-11-01", data_ate="2026-11-30")
    assert s["anterior"]["periodo"] == {"data_de": "2026-10-01", "data_ate": "2026-10-31"}
    assert s["anterior"]["despesas"] == "872.99" and s["anterior"]["variacao_despesas_pct"] == "-50.00"
    assert s["media_6m"]["despesas"] == "872.99"  # só existe outubro: média de 1 mês, não de 6
    assert s["media_6m"]["variacao_despesas_pct"] == "-50.00"


def test_sem_dados(api):
    s = get(api, "summary")
    assert (
        s["despesas"] == "0.00"
        and s["taxa_poupanca_pct"] is None
        and s["anterior"]["variacao_despesas_pct"] is None
    )
    assert get(api, "by-category")["itens"] == []


def test_categorias_existem_para_o_seed(db):
    assert db.scalar(select(Categoria.id).where(Categoria.nome == "Supermercado")) is not None


def test_media_ignora_meses_anteriores_ao_primeiro_movimento(api, db):
    import_all(api)
    out = get(api, "summary", data_de="2026-10-01", data_ate="2026-10-31")
    assert out["media_6m"] == {
        "despesas": None,
        "receitas": None,
        "variacao_despesas_pct": None,
    }  # sem histórico
    assert out["media_12m"]["despesas"] is None
