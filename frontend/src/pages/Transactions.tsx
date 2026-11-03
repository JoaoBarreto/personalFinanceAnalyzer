import { useEffect, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { api, errorMessage, type Category, type Tx, type User } from "../api";
import CategorySelect from "../components/CategorySelect";
import TitularSelect from "../components/TitularSelect";
import { useAsync } from "../hooks";
import { dataPt, eur } from "../lib/format";

type Page = { total: number; page: number; page_size: number; items: Tx[] };

export default function Transactions() {
  const [sp, setSp] = useSearchParams();
  const [q, setQ] = useState(sp.get("q") ?? "");
  useEffect(() => setQ(sp.get("q") ?? ""), [sp]);
  const [err, setErr] = useState<string | null>(null);
  const page = Number(sp.get("page") ?? 1);
  const f = {
    q: sp.get("q") ?? "", titular: sp.get("titular") ?? "", categoria_id: sp.get("categoria_id") ?? "", sem_categoria: sp.get("sem_categoria") ?? "",
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
        <TitularSelect value={f.titular} onChange={(v) => set("titular", v)} />
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
      <div className="card flush">
        <table className="data tx">
          <thead><tr><th>Data</th><th>Descrição</th><th>Categoria</th><th className="num">Montante</th><th className="num hide-sm">Saldo</th></tr></thead>
          <tbody>
            {list.data?.items.map((t) => (
              <tr key={t.id}>
                <td className="c-date">{dataPt(t.data_movimento)}</td>
                <td className="c-desc" title={t.descricao_original}>{t.descricao_normalizada}{t.categoria_origem === "manual" && <span className="tag" title={`Categorizado manualmente${nomeDe(t.atualizado_por) ? ` por ${nomeDe(t.atualizado_por)}` : ""}`}>manual</span>}</td>
                <td className="c-cat">{cats.data && <CategorySelect aria-label={`Categoria de ${t.descricao_normalizada}`} categories={cats.data} value={t.categoria_id} onChange={(id) => setCat(t, id)} />}</td>
                <td className={`num c-amount ${t.montante.startsWith("-") ? "neg" : "pos"}`}>{eur(t.montante)}</td>
                <td className="num muted hide-sm">{eur(t.saldo_apos)}</td>
              </tr>
            ))}
            {list.data?.items.length === 0 && <tr><td colSpan={5} className="muted">Sem movimentos.</td></tr>}
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
