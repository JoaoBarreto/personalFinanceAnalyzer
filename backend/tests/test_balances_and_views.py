"""Saldo da conta, quadro que fecha a conta, vista anual, matriz categoria × mês, continuidade e cobertura."""

from decimal import Decimal as D

from .conftest import ROWS, SALDO_FINAL, SALDO_INICIAL, build_csv
from .test_analytics import get
from .test_categorization_api import cat_id, import_all, txs
from .test_imports import confirm, up

PERIODO = {"data_de": "2026-10-01", "data_ate": "2026-10-31"}


def test_saldo_da_conta_e_quadro_que_fecha(api, db):
    import_all(api)
    s = get(api, "summary", **PERIODO)
    assert s["saldo"] == {
        "inicio": str(SALDO_INICIAL), "fim": str(SALDO_FINAL), "transferencias": "0.00",
        "diferenca": "0.00", "reconcilia": True,
    }  # fmt: skip
    assert D(s["saldo"]["inicio"]) + D(s["receitas"]) - D(s["despesas"]) == D(s["saldo"]["fim"])


def test_quadro_fecha_com_transferencia_dentro_e_fora(api, db):
    import_all(api)
    tid = txs(api, q="SALARIO")["items"][0]["id"]  # +2380,91 como «transferência»
    api.patch(f"/api/transactions/{tid}", json={"categoria_id": cat_id(db, "Transferências entre contas")})
    fora = get(api, "summary", **PERIODO)
    assert fora["receitas"] == "900.00" and fora["saldo"]["transferencias"] == "2380.91"
    assert fora["saldo"]["diferenca"] == "0.00" and fora["saldo"]["reconcilia"] is True
    dentro = get(api, "summary", incluir_transferencias=True, **PERIODO)
    assert (
        dentro["receitas"] == "3280.91" and dentro["saldo"]["transferencias"] == "0.00"
    )  # sem contar duas vezes
    assert dentro["saldo"]["diferenca"] == "0.00"


def test_quadro_acusa_buraco(api, db):
    confirm(api, up(api, build_csv(ROWS[:3])).json()["id"])
    confirm(api, up(api, build_csv(ROWS[5:], saldo_inicial=D("1087.26"))).json()["id"])  # saltou ROWS[3:5]
    s = get(api, "summary", **PERIODO)
    assert s["saldo"]["reconcilia"] is False and s["saldo"]["diferenca"] != "0.00"


def test_abertura_quando_a_conta_comeca_a_meio_do_periodo(api, db):
    import_all(api)
    s = get(api, "summary", data_de="2026-09-01", data_ate="2026-10-31")  # setembro sem movimentos
    assert s["saldo"]["inicio"] == str(SALDO_INICIAL) and s["saldo"]["reconcilia"] is True
    antes = get(api, "summary", data_de="2026-01-01", data_ate="2026-01-31")
    assert antes["saldo"] == {
        "inicio": None,
        "fim": None,
        "transferencias": "0.00",
        "diferenca": None,
        "reconcilia": None,
    }


def test_continuidade_aviso_nao_bloqueia(api, db):
    confirm(api, up(api, build_csv(ROWS[3:], saldo_inicial=D("1229.61"))).json()["id"])  # parte final do mês
    # ficheiro anterior cujo saldo final NÃO encaixa no início do que já está gravado -> aviso, não bloqueio
    p = up(api, build_csv(ROWS[:3], saldo_inicial=D("5000.00"))).json()
    assert any("saldo final do ficheiro" in a for a in p["avisos"])
    assert confirm(api, p["id"]).status_code == 200


def test_continuidade_sem_avisos_quando_encaixa(api, db):
    confirm(api, up(api, build_csv(ROWS[3:], saldo_inicial=D("1229.61"))).json()["id"])
    p = up(api, build_csv(ROWS[:3])).json()  # termina em 1229,61, onde o gravado começa
    assert p["avisos"] == []


def test_cobertura_detecta_e_resolve_buracos(api, db):
    confirm(api, up(api, build_csv(ROWS[:3])).json()["id"])
    confirm(api, up(api, build_csv(ROWS[5:], saldo_inicial=D("1087.26"))).json()["id"])
    c = api.get("/api/coverage").json()[0]
    assert c["ok"] is False and len(c["falhas"]) == 1
    assert (c["falhas"][0]["de"], c["falhas"][0]["ate"]) == ("2026-10-01", "2026-10-03")
    assert c["primeiro"] == "2026-10-01" and c["ultimo"] == "2026-10-10"
    confirm(api, up(api, build_csv(ROWS[3:5], saldo_inicial=D("1229.61"))).json()["id"])  # os que faltavam
    c = api.get("/api/coverage").json()[0]
    assert c["ok"] is True and c["falhas"] == [] and c["n_movimentos"] == len(ROWS)


def test_dia_cortado_a_meio_nao_gera_falso_buraco(api, db):
    confirm(api, up(api, build_csv(ROWS[:2])).json()["id"])  # o dia 01-10 fica a meio (2 de 3 linhas)
    p = up(api, build_csv()).json()
    assert p["resumo"]["duplicado"] == 2 and p["resumo"]["novo"] == len(ROWS) - 2
    confirm(api, p["id"])
    c = api.get("/api/coverage").json()[0]
    assert c["ok"] is True and c["n_movimentos"] == len(ROWS)


def test_cobertura_sem_dados(api):
    c = api.get("/api/coverage").json()[0]
    assert c["n_movimentos"] == 0 and c["ok"] is True and c["primeiro"] is None


def test_vista_anual(api, db):
    import_all(api)
    novo = build_csv(
        [("05-01-2027", "05-01-2027", "COMPRA 0000000.99 LOJA", D("-10.00"))], saldo_inicial=SALDO_FINAL
    )
    confirm(
        api,
        api.post(
            "/api/imports/preview",
            data={"conta_id": api.conta_id},
            files={"file": ("n.csv", novo, "text/csv")},
        ).json()["id"],
    )
    j = get(api, "monthly", granularidade="ano")
    assert j["granularidade"] == "ano" and [x["periodo"] for x in j["periodos"]] == ["2026", "2027"]
    a, b = j["periodos"]
    assert a["despesas"] == "872.99" and a["receitas"] == "3280.91" and a["poupanca"] == "2407.92"
    assert b["despesas"] == "10.00" and b["saldo_fim"] == "3397.92"  # 3407,92 − 10,00
    assert a["saldo_fim"] == "3407.92"


def test_anos_vazios_aparecem_a_zero(api, db):
    import_all(api)
    j = get(api, "monthly", granularidade="ano", data_de="2025-01-01", data_ate="2026-12-31")
    assert [x["periodo"] for x in j["periodos"]] == ["2025", "2026"]
    assert j["periodos"][0]["despesas"] == "0.00" and j["periodos"][0]["saldo_fim"] is None


def test_periodo_anterior_de_um_ano_bissexto(api, db):
    import_all(api)
    s = get(api, "summary", data_de="2028-01-01", data_ate="2028-12-31")  # 2028 é bissexto
    assert s["anterior"]["periodo"] == {"data_de": "2027-01-01", "data_ate": "2027-12-31"}
    s = get(api, "summary", data_de="2026-01-01", data_ate="2026-12-31")
    assert s["anterior"]["periodo"] == {"data_de": "2025-01-01", "data_ate": "2025-12-31"}


def test_matriz_categoria_por_mes(api, db):
    import_all(api)
    import_all(api, [("05-11-2026", "05-11-2026", "COMPRA 0000000.99 LOJA", D("-436.50"))])
    tid = txs(api, q="SUPERMERCADO")["items"][0]["id"]
    api.patch(f"/api/transactions/{tid}", json={"categoria_id": cat_id(db, "Supermercado")})
    m = get(api, "category-matrix", data_de="2026-10-01", data_ate="2026-12-31")
    assert m["meses"] == ["2026-10", "2026-11", "2026-12"]
    por_nome = {linha["nome"]: linha for linha in m["linhas"]}
    assert por_nome["Alimentação"]["valores"]["2026-10"] == "59.75"  # o filho sobe ao pai (nivel=pai)
    assert por_nome["Por categorizar"]["valores"]["2026-11"] == "436.50"
    # não circular: o total de cada mês bate com as despesas do endpoint mensal
    mensal = {
        x["periodo"]: x["despesas"]
        for x in get(api, "monthly", data_de="2026-10-01", data_ate="2026-12-31")["periodos"]
    }
    assert m["totais"] == mensal and m["total"] == "1309.49"  # 872,99 + 436,50
    assert all(isinstance(v, str) for linha in m["linhas"] for v in linha["valores"].values())
    filhos = get(api, "category-matrix", data_de="2026-10-01", data_ate="2026-12-31", nivel="filho")
    assert "Supermercado" in {linha["nome"] for linha in filhos["linhas"]}


def test_matriz_por_omissao_e_o_ano_do_ultimo_movimento(api, db):
    import_all(api)
    m = get(api, "category-matrix")
    assert m["meses"][0] == "2026-01" and m["meses"][-1] == "2026-12" and len(m["meses"]) == 12


def _ano_inteiro():
    """Um ano de movimentos (50 por mês) num só ficheiro, com datas de janeiro a dezembro de 2026."""
    rows = []
    for m in range(1, 13):
        rows.append((f"02-{m:02d}-2026", f"02-{m:02d}-2026", "TRF A CREDITO SEPA+ - EMPRESA X", D("2000.00")))
        for k in range(48):
            d = 3 + k // 3  # dias 3..18
            rows.append(
                (
                    f"{d:02d}-{m:02d}-2026",
                    f"{d:02d}-{m:02d}-2026",
                    f"COMPRA 0000000.{k:02d} LOJA {k}",
                    D("-10.00"),
                )
            )
        rows.append((f"28-{m:02d}-2026", f"28-{m:02d}-2026", "IMPOSTO DO SELO S/ COMISSAO", D("-0.50")))
    return rows


def test_extrato_do_ano_inteiro_separa_por_mes(api, db):
    import time

    rows = _ano_inteiro()
    t0 = time.perf_counter()
    p = up(api, build_csv(rows, saldo_inicial=D("1000.00"))).json()
    assert p["reconciliado"] is True and p["resumo"]["novo"] == len(rows) == 600
    assert confirm(api, p["id"]).json()["n_movimentos"] == 600
    assert time.perf_counter() - t0 < 10  # PRD: ~300 movimentos em < 5 s; aqui 600 com folga

    # cada linha foi parar ao mês da sua data
    j = get(api, "monthly", data_de="2026-01-01", data_ate="2026-12-31")["periodos"]
    assert [x["periodo"] for x in j] == [f"2026-{m:02d}" for m in range(1, 13)]
    assert all(x["receitas"] == "2000.00" and x["despesas"] == "480.50" for x in j)  # 48×10 + 0,50
    assert j[0]["saldo_fim"] == "2519.50" and j[11]["saldo_fim"] == str(D("1000.00") + 12 * D("1519.50"))
    ano = get(api, "monthly", granularidade="ano")["periodos"][0]
    assert (ano["receitas"], ano["despesas"]) == ("24000.00", "5766.00")
    assert get(api, "summary", data_de="2026-03-01", data_ate="2026-03-31")["saldo"]["reconcilia"] is True
    assert get(api, "summary", data_de="2026-01-01", data_ate="2026-12-31")["saldo"]["reconcilia"] is True
    assert api.get("/api/coverage").json()[0]["ok"] is True


def test_mes_avulso_depois_do_ano_inteiro_nao_duplica(api, db):
    rows = _ano_inteiro()
    confirm(api, up(api, build_csv(rows, saldo_inicial=D("1000.00"))).json()["id"])
    marco = [r for r in rows if r[0].endswith("-03-2026")]
    abertura = D("1000.00") + 2 * D("1519.50")  # saldo antes de março
    p = up(api, build_csv(marco, saldo_inicial=abertura)).json()
    assert p["reconciliado"] is True and p["avisos"] == []
    assert p["resumo"] == {"novo": 0, "duplicado": 50, "possivel_duplicado": 0}
    assert confirm(api, p["id"]).json()["n_movimentos"] == 0
    assert api.get("/api/transactions", params={"page_size": 1}).json()["total"] == 600
