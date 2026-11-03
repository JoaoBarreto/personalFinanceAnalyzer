import { useState } from "react";
import { api, errorMessage, type Category } from "../api";
import { useAsync } from "../hooks";

const TIPOS: Record<string, string> = { despesa: "despesa", receita: "receita", transferencia: "transferência" };

function NameInput({ value, onSave }: { value: string; onSave: (v: string) => void }) {
  const [v, setV] = useState(value);
  const commit = () => { const t = v.trim(); if (t && t !== value) onSave(t); else setV(value); };
  return <input value={v} aria-label={`Nome da categoria ${value}`} onChange={(e) => setV(e.target.value)} onBlur={commit}
    onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); if (e.key === "Escape") setV(value); }} />;
}

export default function Categories() {
  const cats = useAsync(() => api.get<Category[]>("/api/categories"), []);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [novoNome, setNovoNome] = useState("");
  const [novoTipo, setNovoTipo] = useState("despesa");
  const [subDe, setSubDe] = useState<number | null>(null);
  const [subNome, setSubNome] = useState("");
  const wrap = async (fn: () => Promise<void>, ok?: string) => {
    try { setErr(null); await fn(); setMsg(ok ?? null); cats.reload(); } catch (e) { setErr(errorMessage(e)); }
  };
  const all = cats.data ?? [];
  const tops = all.filter((c) => c.parent_id === null);

  const row = (c: Category, child: boolean) => (
    <tr key={c.id} className={c.ativa ? "" : "muted"}>
      <td className={child ? "indent" : "strong-cell"}><NameInput value={c.nome} onSave={(nome) => wrap(async () => { await api.patch(`/api/categories/${c.id}`, { nome }); }, "Categoria renomeada.")} /></td>
      <td>{child ? "" : TIPOS[c.tipo] ?? c.tipo}</td>
      <td className="num">{c.n_movimentos ?? 0}</td>
      <td><input type="checkbox" checked={c.ativa} aria-label={`Ativa: ${c.nome}`} onChange={(e) => wrap(async () => { await api.patch(`/api/categories/${c.id}`, { ativa: e.target.checked }); })} /></td>
      <td className="actions">
        {!child && <button className="link" onClick={() => { setSubDe(subDe === c.id ? null : c.id); setSubNome(""); }}>+ subcategoria</button>}
        <button className="link danger" onClick={() => { if (confirm(`Apagar «${c.nome}»? Só é possível se não tiver movimentos, regras nem subcategorias.`)) void wrap(async () => { await api.del(`/api/categories/${c.id}`); }, "Categoria apagada."); }}>Apagar</button>
      </td>
    </tr>
  );

  return (
    <>
      <div className="toolbar"><h1>Categorias</h1></div>
      {msg && <p className="ok" role="status">{msg}</p>}
      {err && <p className="error" role="alert">{err}</p>}
      <form className="card row" onSubmit={(e) => { e.preventDefault(); void wrap(async () => { await api.post("/api/categories", { nome: novoNome, tipo: novoTipo }); setNovoNome(""); }, "Categoria criada."); }}>
        <input placeholder="Nova categoria (ex.: Educação)" value={novoNome} onChange={(e) => setNovoNome(e.target.value)} required />
        <select value={novoTipo} onChange={(e) => setNovoTipo(e.target.value)} aria-label="Tipo">
          <option value="despesa">despesa</option><option value="receita">receita</option><option value="transferencia">transferência (fora dos totais)</option>
        </select>
        <button className="primary">Criar categoria</button>
      </form>
      <div className="card flush">
        <table className="data cats">
          <thead><tr><th>Nome</th><th>Tipo</th><th className="num">Movimentos</th><th>Ativa</th><th /></tr></thead>
          <tbody>
            {tops.map((t) => (
              <>
                {row(t, false)}
                {all.filter((c) => c.parent_id === t.id).map((c) => row(c, true))}
                {subDe === t.id && (
                  <tr key={`new-${t.id}`}><td className="indent" colSpan={5}>
                    <form className="row" onSubmit={(e) => { e.preventDefault(); void wrap(async () => { await api.post("/api/categories", { nome: subNome, parent_id: t.id }); setSubNome(""); setSubDe(null); }, "Subcategoria criada."); }}>
                      <input autoFocus placeholder={`Nova subcategoria de ${t.nome}`} value={subNome} onChange={(e) => setSubNome(e.target.value)} required />
                      <button className="primary">Criar</button><button type="button" onClick={() => setSubDe(null)}>Cancelar</button>
                    </form>
                  </td></tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">Edite o nome e carregue em Enter. Desativar esconde a categoria das listas sem perder o histórico. Uma categoria do tipo «transferência» fica fora das despesas e das receitas.</p>
    </>
  );
}
