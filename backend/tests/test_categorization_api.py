from decimal import Decimal as D

from sqlalchemy import select, text

from app.models import Categoria, Movimento, Regra

from .conftest import N_LINHAS, ROWS, build_csv
from .test_imports import confirm, up


def cat_id(db, nome):
    return db.scalar(select(Categoria.id).where(Categoria.nome == nome))


def mk_rule(api, **kw):
    body = {"padrao": "SUPERMERCADO", "tipo_match": "contem", **kw}
    r = api.post("/api/rules", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def import_all(api, rows=None):
    return confirm(api, up(api, build_csv(rows)).json()["id"]).json()


def txs(api, **params):
    return api.get("/api/transactions", params=params).json()


def test_confirm_categoriza_por_regra(api, db):
    sup = cat_id(db, "Supermercado")
    mk_rule(api, categoria_id=sup)
    import_all(api)
    items = {t["descricao_normalizada"]: t for t in txs(api)["items"]}
    t = items["SUPERMERCADO"]
    assert t["categoria_id"] == sup and t["categoria_origem"] == "regra" and t["regra_id"] is not None
    assert items["EMPRESA X"]["categoria_id"] is None
    assert api.get("/api/rules").json()[0]["n_aplicacoes"] == 1


def test_historico_categoriza_descricao_igual(api, db):
    import_all(api, ROWS[:5])
    sal = cat_id(db, "Salário")
    emp = txs(api, q="EMPRESA")["items"][0]["id"]
    assert api.patch(f"/api/transactions/{emp}", json={"categoria_id": sal}).status_code == 200
    # novo mês com a mesma descrição: o histórico categoriza (sem regra)
    outro = [("05-11-2026", "05-11-2026", "TRF A CREDITO SEPA+ - EMPRESA X", D("900.00"))]
    import_all(api, outro)
    novo = [t for t in txs(api)["items"] if t["data_movimento"] == "2026-11-05"][0]
    assert (
        novo["categoria_id"] == sal and novo["categoria_origem"] == "historico" and novo["regra_id"] is None
    )


def test_manual_nunca_e_sobrescrita(api, db):
    sup, alim = cat_id(db, "Supermercado"), cat_id(db, "Restaurantes")
    import_all(api)
    tid = txs(api, q="SUPERMERCADO")["items"][0]["id"]
    api.patch(f"/api/transactions/{tid}", json={"categoria_id": alim})
    mk_rule(api, categoria_id=sup)
    assert api.post("/api/rules/apply").status_code == 200  # aplicação retroativa
    t = txs(api, q="SUPERMERCADO")["items"][0]
    assert t["categoria_id"] == alim and t["categoria_origem"] == "manual"
    imp = api.post("/api/rules/preview-impact", json={"padrao": "SUPERMERCADO", "categoria_id": sup}).json()
    assert imp == {"afetados": 0, "conflitos": 0}  # manuais não entram na contagem


def test_retroativa_e_preview_impact(api, db):
    sup = cat_id(db, "Supermercado")
    import_all(api)
    assert txs(api, sem_categoria=True)["total"] == N_LINHAS
    imp = api.post("/api/rules/preview-impact", json={"padrao": "supermercado", "categoria_id": sup}).json()
    assert imp == {"afetados": 1, "conflitos": 0}
    r = mk_rule(api, categoria_id=sup)
    assert api.post(f"/api/rules/{r['id']}/preview-impact").json()["afetados"] == 1
    assert api.post("/api/rules/apply").json()["movimentos_alterados"] == 1
    assert txs(api, sem_categoria=True)["total"] == N_LINHAS - 1
    assert api.post("/api/rules/apply").json()["movimentos_alterados"] == 0  # idempotente


def test_conflito_com_outra_categoria_e_sinalizado(api, db):
    sup, alim = cat_id(db, "Supermercado"), cat_id(db, "Restaurantes")
    mk_rule(api, categoria_id=alim, padrao="COMPRA", tipo_match="contem", prioridade=50)
    import_all(api)  # nada contém "COMPRA" depois de normalizado; categoriza por outra regra abaixo
    mk_rule(api, categoria_id=alim, padrao="SUPERMERCADO")
    api.post("/api/rules/apply")
    imp = api.post(
        "/api/rules/preview-impact", json={"padrao": "SUPERMERCADO", "categoria_id": sup, "prioridade": 200}
    )
    assert imp.json() == {"afetados": 1, "conflitos": 1}


def test_validacao_de_regras(api, db):
    sup = cat_id(db, "Supermercado")
    bad = [
        {"padrao": "X", "categoria_id": sup},  # curto
        {"padrao": "(", "tipo_match": "regex", "categoria_id": sup},
        {"padrao": "LIDL", "categoria_id": sup, "montante_min": "10", "montante_max": "5"},
        {"padrao": "LIDL", "categoria_id": 999999},
        {"padrao": "LIDL", "categoria_id": sup, "tipo_match": "xpto"},
    ]
    for b in bad:
        assert api.post("/api/rules", json=b).status_code == 422, b
    r = mk_rule(api, categoria_id=sup, padrao="  Pingo  Doce ")
    assert r["padrao"] == "PINGO DOCE"  # guardado normalizado
    p = api.patch(f"/api/rules/{r['id']}", json={"prioridade": 300, "ativa": False})
    assert p.status_code == 200 and p.json()["prioridade"] == 300 and p.json()["ativa"] is False
    assert api.patch(f"/api/rules/{r['id']}", json={"tipo_match": "regex", "padrao": "("}).status_code == 422
    assert api.delete(f"/api/rules/{r['id']}").status_code == 204


def test_regra_desativada_nao_se_aplica(api, db):
    r = mk_rule(api, categoria_id=cat_id(db, "Supermercado"))
    api.patch(f"/api/rules/{r['id']}", json={"ativa": False})
    import_all(api)
    assert txs(api, q="SUPERMERCADO")["items"][0]["categoria_id"] is None


def test_apagar_regra_mantem_categoria_e_limpa_regra_id(api, db):
    sup = cat_id(db, "Supermercado")
    r = mk_rule(api, categoria_id=sup)
    import_all(api)
    api.delete(f"/api/rules/{r['id']}")
    t = txs(api, q="SUPERMERCADO")["items"][0]
    assert t["categoria_id"] == sup and t["regra_id"] is None


def test_aprendizagem_por_categorizacao_em_grupo(api, db):
    import_all(api)
    g = api.get("/api/transactions/uncategorized", params={"group_by": "description"}).json()
    assert g["total"] == N_LINHAS
    grupo = next(x for x in g["grupos"] if x["descricao_normalizada"] == "SUPERMERCADO")
    assert grupo["n"] == 1 and grupo["keyword_sugerida"] == "SUPERMERCADO" and grupo["total"] == "-59.75"
    sup = cat_id(db, "Supermercado")
    r = api.post(
        "/api/transactions/bulk-categorize",
        json={
            "descricao_normalizada": "SUPERMERCADO",
            "categoria_id": sup,
            "criar_regra": {"padrao": "SUPER"},
        },
    )
    j = r.json()
    assert r.status_code == 200 and j["categorizados"] == 1 and j["regra"]["origem"] == "aprendida"
    assert j["impacto"]["afetados"] >= 0
    t = txs(api, q="SUPERMERCADO")["items"][0]
    assert t["categoria_origem"] == "manual"  # o movimento original fica manual, a regra serve para o futuro
    assert db.scalar(select(Regra.criado_por)) is not None
    # mês seguinte: a regra aprendida categoriza sozinha
    import_all(api, [("07-11-2026", "07-11-2026", "COMPRA 0000000.99 SUPERMERCADO NOVO", D("-10.00"))])
    novo = [t for t in txs(api)["items"] if t["data_movimento"] == "2026-11-07"][0]
    assert novo["categoria_id"] == sup and novo["categoria_origem"] == "regra"


def test_bulk_por_ids_e_seletor_invalido(api, db):
    import_all(api)
    ids = [t["id"] for t in txs(api)["items"][:3]]
    sup = cat_id(db, "Supermercado")
    assert (
        api.post("/api/transactions/bulk-categorize", json={"ids": ids, "categoria_id": sup}).json()[
            "categorizados"
        ]
        == 3
    )
    assert api.post("/api/transactions/bulk-categorize", json={"categoria_id": sup}).status_code == 422
    assert (
        api.post(
            "/api/transactions/bulk-categorize",
            json={"ids": ids, "descricao_normalizada": "X", "categoria_id": sup},
        ).status_code
        == 422
    )
    assert (
        api.post("/api/transactions/bulk-categorize", json={"ids": ids, "categoria_id": 999999}).status_code
        == 422
    )


def test_patch_remove_categoria_e_notas(api, db):
    import_all(api)
    tid = txs(api)["items"][0]["id"]
    sup = cat_id(db, "Supermercado")
    api.patch(f"/api/transactions/{tid}", json={"categoria_id": sup, "notas": "ola"})
    j = api.patch(f"/api/transactions/{tid}", json={"categoria_id": None}).json()
    assert j["categoria_id"] is None and j["categoria_origem"] is None and j["notas"] == "ola"
    assert api.patch("/api/transactions/999999", json={"notas": "x"}).status_code == 404


def test_listagem_filtros_e_paginacao(api, db):
    import_all(api)
    assert txs(api)["total"] == N_LINHAS
    p1 = txs(api, page_size=3, page=1)
    p3 = txs(api, page_size=3, page=3)
    assert len(p1["items"]) == 3 and len(p3["items"]) == N_LINHAS - 6
    assert p1["items"][0]["data_movimento"] >= p1["items"][-1]["data_movimento"]
    assert txs(api, data_de="2026-10-05", data_ate="2026-10-05")["total"] == 1
    assert txs(api, montante_min="500")["total"] == 2  # 900,00 e 2380,91
    assert txs(api, q="comissao")["total"] == 1  # sem acentos
    assert txs(api, q="%")["total"] == 0  # % tratado como literal
    assert all(isinstance(t["montante"], str) for t in txs(api)["items"])


def test_transferencias_podem_ser_excluidas(api, db):
    import_all(api)
    transf = cat_id(db, "Transferências entre contas")
    tid = txs(api, q="EMPRESA")["items"][0]["id"]
    api.patch(f"/api/transactions/{tid}", json={"categoria_id": transf})
    assert txs(api, incluir_transferencias=False)["total"] == N_LINHAS - 1
    assert txs(api)["total"] == N_LINHAS


def test_categorias_dois_niveis_e_heranca_de_tipo(api, db):
    tree = api.get("/api/categories").json()
    alim = next(c for c in tree if c["nome"] == "Alimentação")
    r = api.post("/api/categories", json={"nome": "Talho", "parent_id": alim["id"], "tipo": "receita"})
    assert r.status_code == 201 and r.json()["tipo"] == "despesa"  # herda do pai, ignora o pedido
    assert api.post("/api/categories", json={"nome": "Neto", "parent_id": r.json()["id"]}).status_code == 422
    assert api.post("/api/categories", json={"nome": "Talho", "parent_id": alim["id"]}).status_code == 409
    assert api.post("/api/categories", json={"nome": "Topo"}).status_code == 422
    top = api.post("/api/categories", json={"nome": "Animais", "tipo": "despesa", "cor": "#fff"})
    assert top.status_code == 201
    assert api.patch(f"/api/categories/{top.json()['id']}", json={"ativa": False}).json()["ativa"] is False


def test_categoria_inativa_nao_pode_ser_atribuida(api, db):
    import_all(api)
    c = api.post("/api/categories", json={"nome": "Velha", "tipo": "despesa"}).json()
    api.patch(f"/api/categories/{c['id']}", json={"ativa": False})
    tid = txs(api)["items"][0]["id"]
    assert api.patch(f"/api/transactions/{tid}", json={"categoria_id": c["id"]}).status_code == 422


def test_invariante_categoria_origem(api, db):
    sup = cat_id(db, "Supermercado")
    mk_rule(api, categoria_id=sup)
    import_all(api)
    n = db.scalar(
        text("select count(*) from movimentos where (categoria_id is null) <> (categoria_origem is null)")
    )
    assert n == 0 and db.scalar(select(Movimento.id).limit(1)) is not None
