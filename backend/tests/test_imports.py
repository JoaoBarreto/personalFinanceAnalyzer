import hashlib
import logging
from decimal import Decimal as D

from sqlalchemy import select

from app.models import Importacao, Movimento

from .conftest import N_LINHAS, ROWS, SALDO_FINAL, build_csv


def up(api, content, name="extrato.csv"):
    return api.post(
        "/api/imports/preview", data={"conta_id": api.conta_id}, files={"file": (name, content, "text/csv")}
    )


def confirm(api, imp_id, **body):
    return api.post(f"/api/imports/{imp_id}/confirm", json=body)


def movs(db):
    db.expire_all()
    return db.scalars(select(Movimento).order_by(Movimento.id)).all()


def test_preview_nao_grava_movimentos(api, db):
    r = up(api, build_csv())
    assert r.status_code == 200
    j = r.json()
    assert j["estado"] == "preview" and j["reconciliado"] is True and j["diferenca"] == "0.00"
    assert j["resumo"] == {"novo": N_LINHAS, "duplicado": 0, "possivel_duplicado": 0}
    assert j["ordem_ficheiro"] == "asc" and j["ordem_ambigua"] is False
    assert movs(db) == []


def test_staging_guarda_decimais_como_string(api, db):
    imp_id = up(api, build_csv()).json()["id"]
    st = db.get(Importacao, imp_id).staging["linhas"]
    assert all(isinstance(ln["montante"], str) and isinstance(ln["saldo_apos"], str) for ln in st)
    assert st[0]["data_movimento"] == "2026-10-01"


def test_confirmar_grava_exatamente_os_decimais(api, db):
    imp_id = up(api, build_csv()).json()["id"]
    r = confirm(api, imp_id)
    assert (
        r.status_code == 200 and r.json()["estado"] == "confirmada" and r.json()["n_movimentos"] == N_LINHAS
    )
    ms = movs(db)
    assert [m.montante for m in ms] == [row[3] for row in ROWS]  # Decimal idêntico, sem float
    assert ms[-1].saldo_apos == SALDO_FINAL
    assert all(m.descricao_normalizada and m.categoria_id is None for m in ms)
    assert ms[0].descricao_normalizada == "EMPRESA X" and ms[0].criado_por is not None
    imp = db.get(Importacao, imp_id)
    assert imp.staging is None and imp.confirmada_em is not None


def test_mesmo_ficheiro_bloqueado(api):
    c = build_csv()
    confirm(api, up(api, c).json()["id"])
    assert up(api, c).status_code == 409


def test_periodo_sobreposto_so_insere_novas(api, db):
    confirm(api, up(api, build_csv(ROWS[:5])).json()["id"])
    p = up(api, build_csv()).json()
    assert p["resumo"] == {"novo": N_LINHAS - 5, "duplicado": 5, "possivel_duplicado": 0}
    r = confirm(api, p["id"]).json()
    assert r["n_movimentos"] == N_LINHAS - 5 and r["n_duplicados_ignorados"] == 5
    assert [m.montante for m in movs(db)] == [row[3] for row in ROWS[:5]] + [row[3] for row in ROWS[5:]]


def test_correcao_e_revalidada_no_confirm(api, db):
    bad = build_csv().replace(b'"-2,25",EUR,"1897,75"', b'"-2,26",EUR,"1897,75"')
    p = up(api, bad).json()
    assert p["reconciliado"] is False and p["diferenca"] != "0.00"
    r = confirm(api, p["id"])
    assert r.status_code == 422 and r.json()["detail"]["quebras"][0]["linha"] == 1
    db.expire_all()
    imp = db.get(Importacao, p["id"])
    assert imp.estado == "preview" and imp.reconciliado is False and imp.diferenca != 0
    assert movs(db) == []
    ok = confirm(api, p["id"], correcoes={"1": {"montante": "-2.25"}})
    assert ok.status_code == 200
    assert D("-2.25") in [m.montante for m in movs(db)]


def test_exclusao_nao_quebra_a_cadeia(api, db):
    r = confirm(api, up(api, build_csv()).json()["id"], linhas_excluidas=[3])
    assert r.status_code == 200 and r.json()["n_movimentos"] == N_LINHAS - 1
    assert r.json()["n_excluidos_utilizador"] == 1 and len(movs(db)) == N_LINHAS - 1


def test_possiveis_duplicados_por_omissao_nao_gravados(api, db):
    confirm(api, up(api, build_csv(ROWS[:3])).json()["id"])
    outro = build_csv(ROWS[:3], saldo_inicial=D("2000.00"))  # mesmas chaves, saldos diferentes
    p = up(api, outro).json()
    assert p["resumo"]["possivel_duplicado"] == 3 and p["avisos"]
    r = confirm(api, p["id"]).json()
    assert r["n_movimentos"] == 0 and r["n_duplicados_ignorados"] == 3
    p2 = up(api, build_csv(ROWS[:3], saldo_inicial=D("3000.00"))).json()
    r2 = confirm(api, p2["id"], incluir_possiveis_duplicados=[0, 1, 2]).json()
    assert r2["n_movimentos"] == 3 and len(movs(db)) == 6


def test_aviso_de_continuidade(api):
    confirm(api, up(api, build_csv(ROWS[:3])).json()["id"])
    p = up(api, build_csv(ROWS[5:], saldo_inicial=D("5000.00"))).json()
    assert any("saldo inicial" in a for a in p["avisos"])


def test_reversao_e_bloqueio_por_importacao_posterior(api, db):
    a = confirm(api, up(api, build_csv(ROWS[:5])).json()["id"]).json()["id"]
    b = confirm(api, up(api, build_csv()).json()["id"]).json()["id"]
    assert api.delete(f"/api/imports/{a}").status_code == 409  # B sobrepõe-se e é posterior
    assert api.delete(f"/api/imports/{b}").status_code == 204
    assert len(movs(db)) == 5
    assert api.delete(f"/api/imports/{a}").status_code == 204
    assert movs(db) == []
    db.expire_all()
    assert db.get(Importacao, a).estado == "revertida" and db.get(Importacao, a).revertida_por is not None
    # depois de revertido, o mesmo ficheiro pode ser reimportado
    assert up(api, build_csv(ROWS[:5])).status_code == 200


def test_cancelar_preview_apaga(api, db):
    imp_id = up(api, build_csv()).json()["id"]
    assert api.delete(f"/api/imports/{imp_id}").status_code == 204
    assert db.get(Importacao, imp_id) is None


def test_confirmar_duas_vezes(api):
    imp_id = up(api, build_csv()).json()["id"]
    assert confirm(api, imp_id).status_code == 200
    assert confirm(api, imp_id).status_code == 409


def test_ficheiro_invalido_fica_em_erro(api, db):
    r = up(api, b"a,b,c\n1,2,3\n")
    assert r.status_code == 422
    imp = db.scalars(select(Importacao)).one()
    assert imp.estado == "erro" and imp.erro_detalhe


def test_rejeicoes_de_upload(api):
    assert up(api, b"PK\x03\x04xlsx").status_code == 415
    assert up(api, b"%PDF-1.7").status_code == 415
    assert up(api, b"a\x00b").status_code == 415
    assert up(api, b"x" * (10 * 1024 * 1024 + 1)).status_code == 413


def test_indice_invalido(api):
    imp_id = up(api, build_csv()).json()["id"]
    assert confirm(api, imp_id, linhas_excluidas=[99]).status_code == 422


def test_csrf_exigido_no_upload(api):
    del api.headers["X-CSRF-Token"]
    assert up(api, build_csv()).status_code == 403


def test_logs_sem_descricoes_nem_montantes(api, caplog):
    caplog.set_level(logging.DEBUG)
    imp_id = up(api, build_csv()).json()["id"]
    confirm(api, imp_id)
    api.delete(f"/api/imports/{imp_id}")
    text = caplog.text
    assert "EMPRESA X" not in text and "SUPERMERCADO" not in text and "2380" not in text


def test_hash_do_ficheiro_guardado(api, db):
    c = build_csv()
    imp = db.get(Importacao, up(api, c).json()["id"])
    assert imp.ficheiro_hash == hashlib.sha256(c).hexdigest()


def test_dinheiro_na_api_nunca_e_float(api):
    j = up(api, build_csv()).json()
    assert (
        j["saldo_inicial"] == "1000.00" and j["saldo_final"] == str(SALDO_FINAL) and j["diferenca"] == "0.00"
    )
    assert all(isinstance(ln["montante"], str) for ln in j["linhas"])
    done = confirm(api, j["id"]).json()
    assert isinstance(done["saldo_final"], str)


def test_reversao_segue_a_ordem_de_confirmacao_e_nao_de_criacao(api, db):
    x = up(api, build_csv(ROWS[:5])).json()["id"]  # criada primeiro
    y = up(api, build_csv()).json()["id"]
    assert y > x
    assert confirm(api, y).json()["n_movimentos"] == N_LINHAS  # Y confirmada primeiro: é dona das linhas
    assert confirm(api, x).json()["n_duplicados_ignorados"] == 5  # X é toda duplicada
    assert api.delete(f"/api/imports/{y}").status_code == 409  # X é posterior (confirmada depois)
    assert len(movs(db)) == N_LINHAS
    assert api.delete(f"/api/imports/{x}").status_code == 204
    assert api.delete(f"/api/imports/{y}").status_code == 204
    assert movs(db) == []


def test_previews_expiradas_sao_apagadas(api, db):
    from datetime import UTC, datetime, timedelta

    old = up(api, build_csv(ROWS[:3])).json()["id"]
    imp = db.get(Importacao, old)
    imp.expira_em = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    db.expire_all()
    up(api, build_csv(ROWS[:4]))  # qualquer novo preview dispara a limpeza
    assert db.get(Importacao, old) is None
