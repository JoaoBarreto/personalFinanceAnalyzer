import { useState } from "react";
import { api, errorMessage, type Category } from "../api";
import CategorySelect from "../components/CategorySelect";
import { useAsync } from "../hooks";

type Rule = { id: number; padrao: string; tipo_match: string; categoria_id: number; direcao: string; prioridade: number; origem: string; ativa: boolean; n_aplicacoes: number };
type Impact = { afetados: number; conflitos: number };

export default function Rules() {
  const cats = useAsync(() => api.get<Category[]>("/api/categories"), []);
  const rules = useAsync(() => api.get<Rule[]>("/api/rules"), []);
  const [padrao, setPadrao] = useState("");
  const [tipo, setTipo] = useState("contem");
  const [cat, setCat] = useState<number | null>(null);
  const [prio, setPrio] = useState(100);
  const [impact, setImpact] = useState<Impact | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const catName = (id: number) => cats.data?.find((c) => c.id === id)?.nome ?? `#${id}`;
  const wrap = async (fn: () => Promise<void>) => { try { setErr(null); await fn(); } catch (e) { setErr(errorMessage(e)); } };
  const draft = () => ({ padrao, tipo_match: tipo, categoria_id: cat, prioridade: prio });
  return (
    <>
      <div className="toolbar">
        <h1>Regras</h1>
        <button onClick={() => wrap(async () => { const r = await api.post<{ movimentos_alterados: number }>("/api/rules/apply"); setMsg(`${r.movimentos_alterados} movimento(s) atualizados (manuais ignorados).`); })}>
          Aplicar a movimentos existentes
        </button>
      </div>
      {msg && <p className="ok" role="status">{msg}</p>}
      {err && <p className="error" role="alert">{err}</p>}
      <form className="card row" onSubmit={(e) => { e.preventDefault(); void wrap(async () => { await api.post("/api/rules", draft()); setPadrao(""); setImpact(null); rules.reload(); }); }}>
        <input placeholder="Palavra-chave (ex.: FNAC)" value={padrao} onChange={(e) => { setPadrao(e.target.value); setImpact(null); }} required />
        <select value={tipo} onChange={(e) => setTipo(e.target.value)} aria-label="Tipo">
          <option value="contem">contém</option><option value="comeca_por">começa por</option>
        </select>
        {cats.data && <CategorySelect categories={cats.data} value={cat} onChange={setCat} emptyLabel="Categoria…" aria-label="Categoria" />}
        <label>Prioridade <input type="number" value={prio} onChange={(e) => setPrio(Number(e.target.value))} style={{ width: "5rem" }} /></label>
        <button type="button" disabled={!cat || !padrao} onClick={() => wrap(async () => setImpact(await api.post<Impact>("/api/rules/preview-impact", draft())))}>Ver impacto</button>
        <button className="primary" disabled={!cat || !padrao}>Criar regra</button>
        {impact && <span className={impact.conflitos ? "warn-text" : "muted"}>Afetaria {impact.afetados} movimento(s){impact.conflitos ? `, ${impact.conflitos} com outra categoria` : ""}.</span>}
      </form>
      <div className="card flush">
        <table className="data">
          <thead><tr><th>Palavra-chave</th><th>Tipo</th><th>Categoria</th><th className="num">Prioridade</th><th>Origem</th><th className="num">Aplicações</th><th>Ativa</th><th /></tr></thead>
          <tbody>
            {rules.data?.map((r) => (
              <tr key={r.id} className={r.ativa ? "" : "muted"}>
                <td>{r.padrao}</td><td>{r.tipo_match === "contem" ? "contém" : r.tipo_match === "comeca_por" ? "começa por" : r.tipo_match}</td>
                <td>{catName(r.categoria_id)}</td><td className="num">{r.prioridade}</td><td>{r.origem}</td><td className="num">{r.n_aplicacoes}</td>
                <td><input type="checkbox" checked={r.ativa} aria-label={`Ativar ${r.padrao}`} onChange={(e) => wrap(async () => { await api.patch(`/api/rules/${r.id}`, { ativa: e.target.checked }); rules.reload(); })} /></td>
                <td><button className="link danger" onClick={() => { if (confirm(`Apagar a regra «${r.padrao}»? As categorias já atribuídas mantêm-se.`)) void wrap(async () => { await api.del(`/api/rules/${r.id}`); rules.reload(); }); }}>Apagar</button></td>
              </tr>
            ))}
            {rules.data?.length === 0 && <tr><td colSpan={8} className="muted">Ainda não há regras. Criam-se aqui ou ao categorizar em «Por categorizar».</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  );
}
