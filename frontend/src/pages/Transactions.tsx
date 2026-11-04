import { useEffect, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { api, errorMessage, type Category, type Tx, type User } from "../api";
import CategorySelect from "../components/CategorySelect";
import { useAsync } from "../hooks";
import { dataPt, eur } from "../lib/format";
import { suggestKeyword } from "../lib/keyword";

type Page = { total: number; page: number; page_size: number; items: Tx[] };
type Changed = { id: number; anterior: { categoria_id: number | null; categoria_origem: string | null; regra_id: number | null } };
type BulkResult = { categorizados: number; aplicados: number; regra: { id: number } | null; alteradas: Changed[] };

export default function Transactions() {
  const [sp, setSp] = useSearchParams();
  const [q, setQ] = useState(sp.get("q") ?? "");
  useEffect(() => setQ(sp.get("q") ?? ""), [sp]);
  const [err, setErr] = useState<string | null>(null);
  const page = Number(sp.get("page") ?? 1);
  const f = {
    q: sp.get("q") ?? "", categoria_id: sp.get("categoria_id") ?? "", sem_categoria: sp.get("sem_categoria") ?? "",
    data_de: sp.get("data_de") ?? "", data_ate: sp.get("data_ate") ?? "", incluir_transferencias: sp.get("transf") ?? "true",
    montante_max: sp.get("so_despesas") ? "-0.01" : "", page,
  };
  const nav = useNavigate();
  const fromDashboard = (useLocation().state as { from?: string } | null)?.from === "dashboard";
  const set = (k: string, v: string) => {
    const n = new URLSearchParams(sp);
    if (v) n.set(k, v); else n.delete(k);
    if (k !== "page") n.delete("page");
    setSp(n);
  };
  const cats = useAsync(() => api.get<Category[]>("/api/categories"), []);
  const users = useAsync(() => api.get<User[]>("/api/users"), []);
  const nomeDe = (id: number | null) => users.data?.find((u) => u.id === id)?.nome;
  const list = useAsync(() => api.get<Page>("/api/transactions", { ...f, page_size: 50 }), [sp.toString()]);
  const setCat = async (t: Tx, id: number | null) => {
    try {
      await api.patch(`/api/transactions/${t.id}`, { categoria_id: id });
      list.reload();
    } catch (e) {
      setErr(errorMessage(e));
    }
  };
  // --- seleção múltipla e categorização em lote ---
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [bulkCat, setBulkCat] = useState<number | null>(null);
  const [makeRule, setMakeRule] = useState(false);
  const [kw, setKw] = useState("");
  const [tipo, setTipo] = useState<"contem" | "comeca_por">("comeca_por");
  const [done, setDone] = useState<{ msg: string; alteradas: Changed[]; regraId: number | null } | null>(null);
  useEffect(() => { setSel(new Set()); }, [sp.toString()]);
  const items = list.data?.items ?? [];
  const firstSel = items.find((t) => sel.has(t.id));
  useEffect(() => { if (makeRule && firstSel) setKw(suggestKeyword(firstSel.descricao_normalizada)); }, [makeRule, firstSel?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const toggle = (id: number) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const allOnPage = items.length > 0 && items.every((t) => sel.has(t.id));
  const selectAllFiltered = async () => {
    try {
      const ids: number[] = [];
      for (let p = 1; ids.length < (list.data?.total ?? 0) && p <= 20; p++) {
        const r = await api.get<Page>("/api/transactions", { ...f, page: p, page_size: 200 });
        ids.push(...r.items.map((t) => t.id));
      }
      setSel(new Set(ids));
    } catch (e) { setErr(errorMessage(e)); }
  };
  const applyBulk = async () => {
    if (!bulkCat) return setErr("Escolha a categoria.");
    try {
      setErr(null);
      const r = await api.post<BulkResult>("/api/transactions/bulk-categorize", {
        ids: [...sel], categoria_id: bulkCat,
        criar_regra: makeRule ? { padrao: kw, tipo_match: tipo, aplicar_retroativamente: true } : undefined,
      });
      const nome = cats.data?.find((c) => c.id === bulkCat)?.nome ?? "";
      setDone({ msg: `${r.categorizados} linha(s) categorizada(s) como «${nome}»${r.aplicados ? ` + ${r.aplicados} de outras descrições pela nova regra` : ""}.`, alteradas: r.alteradas, regraId: r.regra?.id ?? null });
      setSel(new Set()); setBulkCat(null); setMakeRule(false);
      list.reload();
    } catch (e) { setErr(errorMessage(e)); }
  };
  const undo = async () => {
    if (!done) return;
    try {
      await api.post("/api/transactions/restore", { itens: done.alteradas.map((a) => ({ id: a.id, ...a.anterior })), apagar_regra_id: done.regraId });
      setDone(null); list.reload();
    } catch (e) { setErr(errorMessage(e)); }
  };
  const remove = (keys: string[]) => { const n = new URLSearchParams(sp); keys.forEach((k) => n.delete(k)); n.delete("page"); setSp(n); };
  const catNome = cats.data?.find((c) => String(c.id) === f.categoria_id)?.nome;
  const chips: { label: string; keys: string[] }[] = [
    f.categoria_id ? { label: `Categoria: ${catNome ?? f.categoria_id}`, keys: ["categoria_id"] } : null,
    f.sem_categoria ? { label: "Por categorizar", keys: ["sem_categoria"] } : null,
    f.data_de || f.data_ate ? { label: `Período: ${f.data_de ? dataPt(f.data_de) : "…"} – ${f.data_ate ? dataPt(f.data_ate) : "…"}`, keys: ["data_de", "data_ate"] } : null,
    sp.get("so_despesas") ? { label: "Só despesas", keys: ["so_despesas"] } : null,
    sp.get("transf") === "false" ? { label: "Sem transferências", keys: ["transf"] } : null,
    f.q ? { label: `Pesquisa: ${f.q}`, keys: ["q"] } : null,
  ].filter((x): x is { label: string; keys: string[] } => x !== null);
  const pages = list.data ? Math.max(1, Math.ceil(list.data.total / list.data.page_size)) : 1;
  return (
    <>
      <div className="toolbar">
        <h1>Movimentos</h1>
        <form onSubmit={(e) => { e.preventDefault(); set("q", q); }}>
          <input type="search" placeholder="Pesquisar…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Pesquisar" />
        </form>
        <label>De <input type="date" value={f.data_de} onChange={(e) => set("data_de", e.target.value)} /></label>
        <label>Até <input type="date" value={f.data_ate} onChange={(e) => set("data_ate", e.target.value)} /></label>
        {cats.data && (
          <CategorySelect aria-label="Categoria" categories={cats.data} value={f.categoria_id ? Number(f.categoria_id) : null}
            onChange={(id) => set("categoria_id", id ? String(id) : "")} emptyLabel="Todas as categorias" />
        )}
        <label className="check"><input type="checkbox" checked={f.sem_categoria === "true"} onChange={(e) => set("sem_categoria", e.target.checked ? "true" : "")} /> Por categorizar</label>
      </div>
      {chips.length > 0 && (
        <div className="chips" aria-label="Filtros ativos">
          {fromDashboard && <button className="link" onClick={() => nav(-1)}>← Voltar ao dashboard</button>}
          {chips.map((c) => (
            <button key={c.label} className="chip" onClick={() => remove(c.keys)} title="Remover este filtro">{c.label} ×</button>
          ))}
          <button className="link" onClick={() => setSp(new URLSearchParams())}>Limpar filtros</button>
        </div>
      )}
      {(err || list.error) && <p className="error" role="alert">{err ?? list.error}</p>}
      {done && (
        <div className="card last" role="status">
          <strong className="ok">{done.msg}</strong>{" "}
          <button onClick={undo}>Desfazer</button>{" "}
          <button className="link" onClick={() => setDone(null)} aria-label="Fechar">✕</button>
        </div>
      )}
      {sel.size > 0 && (
        <div className="card bulkbar" role="region" aria-label="Categorizar selecionadas">
          <strong>{sel.size} selecionada(s)</strong>
          {list.data && sel.size < list.data.total && <button className="link" onClick={selectAllFiltered}>Selecionar as {list.data.total} do filtro</button>}
          {cats.data && <CategorySelect aria-label="Categoria para as selecionadas" categories={cats.data} value={bulkCat} onChange={setBulkCat} emptyLabel="Categoria…" />}
          <label className="check"><input type="checkbox" checked={makeRule} onChange={(e) => setMakeRule(e.target.checked)} /> Criar regra</label>
          {makeRule && (
            <>
              <input aria-label="Palavra-chave" value={kw} onChange={(e) => setKw(e.target.value)} style={{ width: "10rem" }} />
              <select aria-label="Tipo" value={tipo} onChange={(e) => setTipo(e.target.value as "contem" | "comeca_por")}>
                <option value="comeca_por">começa por</option><option value="contem">contém</option>
              </select>
            </>
          )}
          <button className="primary" disabled={!bulkCat} onClick={applyBulk}>Categorizar {sel.size}</button>
          <button className="link" onClick={() => setSel(new Set())}>Limpar seleção</button>
        </div>
      )}
      <div className="card flush">
        <table className="data tx">
          <thead><tr><th className="c-sel"><input type="checkbox" aria-label="Selecionar todas as desta página" checked={allOnPage} onChange={() => setSel(allOnPage ? new Set() : new Set(items.map((t) => t.id)))} /></th><th>Data</th><th>Descrição</th><th>Categoria</th><th className="num">Montante</th><th className="num hide-sm">Saldo</th></tr></thead>
          <tbody>
            {list.data?.items.map((t) => (
              <tr key={t.id} className={sel.has(t.id) ? "selected" : ""}>
                <td className="c-sel"><input type="checkbox" aria-label={`Selecionar ${t.descricao_normalizada}`} checked={sel.has(t.id)} onChange={() => toggle(t.id)} /></td>
                <td className="c-date">{dataPt(t.data_movimento)}</td>
                <td className="c-desc" title={t.descricao_original}>{t.descricao_normalizada}{t.categoria_origem === "manual" && <span className="tag" title={`Categorizado manualmente${nomeDe(t.atualizado_por) ? ` por ${nomeDe(t.atualizado_por)}` : ""}`}>manual</span>}</td>
                <td className="c-cat">{cats.data && <CategorySelect aria-label={`Categoria de ${t.descricao_normalizada}`} categories={cats.data} value={t.categoria_id} onChange={(id) => setCat(t, id)} />}</td>
                <td className={`num c-amount ${t.montante.startsWith("-") ? "neg" : "pos"}`}>{eur(t.montante)}</td>
                <td className="num muted hide-sm">{eur(t.saldo_apos)}</td>
              </tr>
            ))}
            {list.data?.items.length === 0 && <tr><td colSpan={6} className="muted">Sem movimentos.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="pager">
        <button disabled={page <= 1} onClick={() => set("page", String(page - 1))}>← Anterior</button>
        <span>Página {page} de {pages} · {list.data?.total ?? 0} movimentos</span>
        <button disabled={page >= pages} onClick={() => set("page", String(page + 1))}>Seguinte →</button>
      </div>
    </>
  );
}
