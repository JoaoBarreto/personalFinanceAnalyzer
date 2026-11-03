import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, errorMessage, type Category } from "../api";
import CategorySelect from "../components/CategorySelect";
import { useAsync } from "../hooks";

type Rule = {
  id: number; padrao: string; tipo_match: string; categoria_id: number; categoria_nome: string; direcao: string;
  prioridade: number; origem: string; ativa: boolean; n_aplicacoes: number;
};
type RulesPage = { total: number; page: number; page_size: number; items: Rule[] };
type Impact = { afetados: number; conflitos: number };

const PAGE_SIZE = 25;
const TIPO: Record<string, string> = { contem: "contém", comeca_por: "começa por", igual: "igual a", regex: "regex" };

export default function Rules() {
  const [sp, setSp] = useSearchParams();
  const q = sp.get("q") ?? "";
  const categoria = sp.get("categoria_id") ?? "";
  const origem = sp.get("origem") ?? "";
  const ativa = sp.get("ativa") ?? "";
  const page = Number(sp.get("page") ?? 1);
  const [qText, setQText] = useState(q);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [pending, setPending] = useState<{ rule: Rule; afetados: number } | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState({ padrao: "", tipo_match: "contem", prioridade: 100 });
  // formulário de nova regra
  const [padrao, setPadrao] = useState("");
  const [tipo, setTipo] = useState("contem");
  const [cat, setCat] = useState<number | null>(null);
  const [prio, setPrio] = useState(100);
  const [impact, setImpact] = useState<Impact | null>(null);

  const cats = useAsync(() => api.get<Category[]>("/api/categories"), []);
  const list = useAsync(
    () => api.get<RulesPage>("/api/rules/search", { q, categoria_id: categoria, origem, ativa, page, page_size: PAGE_SIZE }),
    [sp.toString()],
  );

  const setParam = (k: string, v: string) =>
    setSp((prev) => {
      const n = new URLSearchParams(prev);
      if (v) n.set(k, v); else n.delete(k);
      if (k !== "page") n.delete("page"); // mudar um filtro volta à 1.ª página
      return n;
    }, { replace: true });
  // pesquisa com pequena espera, para não pedir a cada tecla
  useEffect(() => {
    const t = setTimeout(() => { if (qText !== q) setParam("q", qText); }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qText]);

  const wrap = async (fn: () => Promise<void>) => { try { setErr(null); await fn(); } catch (e) { setErr(errorMessage(e)); } };
  const pages = list.data ? Math.max(1, Math.ceil(list.data.total / list.data.page_size)) : 1;

  const changeCategory = (r: Rule, id: number | null) => wrap(async () => {
    if (id === null || id === r.categoria_id) return;
    await api.patch(`/api/rules/${r.id}`, { categoria_id: id });
    list.reload();
    // os movimentos que a regra já categorizou mantêm a categoria antiga até se aplicar: dizer quantos são
    const imp = await api.post<Impact>(`/api/rules/${r.id}/preview-impact`);
    setMsg(null);
    setPending(imp.afetados > 0 ? { rule: { ...r, categoria_id: id }, afetados: imp.afetados } : null);
    if (imp.afetados === 0) setMsg("Categoria da regra atualizada.");
  });
  const applyAll = () => wrap(async () => {
    const r = await api.post<{ movimentos_alterados: number }>("/api/rules/apply");
    setPending(null);
    setMsg(`${r.movimentos_alterados} movimento(s) atualizados (categorizações manuais nunca são alteradas).`);
  });
  const startEdit = (r: Rule) => { setEditing(r.id); setDraft({ padrao: r.padrao, tipo_match: r.tipo_match, prioridade: r.prioridade }); };
  const saveEdit = (r: Rule) => wrap(async () => {
    await api.patch(`/api/rules/${r.id}`, draft);
    setEditing(null);
    setMsg("Regra atualizada. Para aplicar a alteração aos movimentos já importados, use «Aplicar a movimentos existentes».");
    list.reload();
  });

  const newDraft = () => ({ padrao, tipo_match: tipo, categoria_id: cat, prioridade: prio });
  return (
    <>
      <div className="toolbar">
        <h1>Regras</h1>
        <button onClick={() => applyAll()}>Aplicar a movimentos existentes</button>
      </div>
      {msg && <p className="ok" role="status">{msg}</p>}
      {err && <p className="error" role="alert">{err}</p>}
      {pending && (
        <div className="card warn-card" role="status">
          A regra «{pending.rule.padrao}» passou a categorizar como <strong>{cats.data?.find((c) => c.id === pending.rule.categoria_id)?.nome}</strong>.
          Há {pending.afetados} movimento(s) que ainda têm a categoria antiga.{" "}
          <button className="primary" onClick={applyAll}>Aplicar agora</button>{" "}
          <button className="link" onClick={() => setPending(null)}>Agora não</button>
        </div>
      )}

      <details className="card newrule">
        <summary>Nova regra</summary>
        <form className="row" onSubmit={(e) => { e.preventDefault(); void wrap(async () => { await api.post("/api/rules", newDraft()); setPadrao(""); setImpact(null); setMsg("Regra criada."); list.reload(); }); }}>
          <input placeholder="Palavra-chave (ex.: FNAC)" value={padrao} onChange={(e) => { setPadrao(e.target.value); setImpact(null); }} required />
          <select value={tipo} onChange={(e) => setTipo(e.target.value)} aria-label="Tipo">
            <option value="contem">contém</option><option value="comeca_por">começa por</option><option value="igual">igual a</option>
          </select>
          {cats.data && <CategorySelect categories={cats.data} value={cat} onChange={setCat} emptyLabel="Categoria…" aria-label="Categoria" />}
          <label>Prioridade <input type="number" value={prio} onChange={(e) => setPrio(Number(e.target.value))} style={{ width: "5rem" }} /></label>
          <button type="button" disabled={!cat || !padrao} onClick={() => wrap(async () => setImpact(await api.post<Impact>("/api/rules/preview-impact", newDraft())))}>Ver impacto</button>
          <button className="primary" disabled={!cat || !padrao}>Criar regra</button>
          {impact && <span className={impact.conflitos ? "warn-text" : "muted"}>Afetaria {impact.afetados} movimento(s){impact.conflitos ? `, ${impact.conflitos} com outra categoria` : ""}.</span>}
        </form>
      </details>

      <div className="toolbar filters">
        <input type="search" placeholder="Pesquisar regras (palavra-chave ou categoria)…" value={qText} onChange={(e) => setQText(e.target.value)} aria-label="Pesquisar regras" style={{ minWidth: "18rem" }} />
        {cats.data && <CategorySelect aria-label="Categoria" categories={cats.data} value={categoria ? Number(categoria) : null} onChange={(id) => setParam("categoria_id", id ? String(id) : "")} emptyLabel="Todas as categorias" />}
        <select aria-label="Origem" value={origem} onChange={(e) => setParam("origem", e.target.value)}>
          <option value="">Todas as origens</option><option value="manual">manuais</option><option value="aprendida">aprendidas</option>
        </select>
        <select aria-label="Estado" value={ativa} onChange={(e) => setParam("ativa", e.target.value)}>
          <option value="">Ativas e inativas</option><option value="true">só ativas</option><option value="false">só inativas</option>
        </select>
        {(q || categoria || origem || ativa) && <button className="link" onClick={() => { setQText(""); setSp(new URLSearchParams(), { replace: true }); }}>Limpar filtros</button>}
      </div>

      <div className="card flush">
        <table className="data rules">
          <thead><tr><th>Palavra-chave</th><th>Tipo</th><th>Categoria</th><th className="num">Prioridade</th><th>Origem</th><th className="num">Aplicações</th><th>Ativa</th><th /></tr></thead>
          <tbody>
            {list.data?.items.map((r) => {
              const ed = editing === r.id;
              return (
                <tr key={r.id} className={r.ativa ? "" : "muted"}>
                  <td>{ed ? <input aria-label="Palavra-chave" value={draft.padrao} onChange={(e) => setDraft({ ...draft, padrao: e.target.value })} /> : r.padrao}</td>
                  <td>{ed ? (
                    <select aria-label="Tipo" value={draft.tipo_match} onChange={(e) => setDraft({ ...draft, tipo_match: e.target.value })}>
                      <option value="contem">contém</option><option value="comeca_por">começa por</option><option value="igual">igual a</option>
                    </select>
                  ) : TIPO[r.tipo_match] ?? r.tipo_match}</td>
                  <td>{cats.data && <CategorySelect aria-label={`Categoria da regra ${r.padrao}`} categories={cats.data} value={r.categoria_id} onChange={(id) => changeCategory(r, id)} emptyLabel={r.categoria_nome} />}</td>
                  <td className="num">{ed ? <input type="number" aria-label="Prioridade" value={draft.prioridade} onChange={(e) => setDraft({ ...draft, prioridade: Number(e.target.value) })} style={{ width: "5rem" }} /> : r.prioridade}</td>
                  <td>{r.origem}</td><td className="num">{r.n_aplicacoes}</td>
                  <td><input type="checkbox" checked={r.ativa} aria-label={`Ativar ${r.padrao}`} onChange={(e) => wrap(async () => { await api.patch(`/api/rules/${r.id}`, { ativa: e.target.checked }); list.reload(); })} /></td>
                  <td className="actions">
                    {ed ? (<><button className="link" onClick={() => saveEdit(r)}>Guardar</button><button className="link" onClick={() => setEditing(null)}>Cancelar</button></>)
                        : (<><button className="link" onClick={() => startEdit(r)}>Editar</button>
                            <button className="link danger" onClick={() => { if (confirm(`Apagar a regra «${r.padrao}»? As categorias já atribuídas mantêm-se.`)) void wrap(async () => { await api.del(`/api/rules/${r.id}`); list.reload(); }); }}>Apagar</button></>)}
                  </td>
                </tr>
              );
            })}
            {list.data?.items.length === 0 && <tr><td colSpan={8} className="muted">{q || categoria || origem || ativa ? "Nenhuma regra corresponde à pesquisa." : "Ainda não há regras. Criam-se aqui ou ao categorizar em «Por categorizar»."}</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="pager">
        <button disabled={page <= 1} onClick={() => setParam("page", String(page - 1))}>← Anterior</button>
        <span>Página {page} de {pages} · {list.data?.total ?? 0} regra(s)</span>
        <button disabled={page >= pages} onClick={() => setParam("page", String(page + 1))}>Seguinte →</button>
      </div>
    </>
  );
}
