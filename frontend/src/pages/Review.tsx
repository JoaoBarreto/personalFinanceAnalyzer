import { useState } from "react";
import { api, errorMessage, type Category } from "../api";
import CategorySelect from "../components/CategorySelect";
import { useAsync } from "../hooks";
import { eur } from "../lib/format";

type Group = { descricao_normalizada: string; n: number; total: string; exemplo_original: string; keyword_sugerida: string };
type Impact = { afetados: number; conflitos: number };

function GroupRow({ g, cats, onDone }: { g: Group; cats: Category[]; onDone: (msg: string) => void }) {
  const [cat, setCat] = useState<number | null>(null);
  const [kw, setKw] = useState(g.keyword_sugerida);
  const [tipo, setTipo] = useState<"contem" | "comeca_por">("contem");
  const [learn, setLearn] = useState(true);
  const [retro, setRetro] = useState(false);
  const [impact, setImpact] = useState<Impact | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const preview = async () => {
    if (!cat) return setErr("Escolha primeiro a categoria.");
    try {
      setErr(null);
      setImpact(await api.post<Impact>("/api/rules/preview-impact", { padrao: kw, tipo_match: tipo, categoria_id: cat }));
    } catch (e) { setErr(errorMessage(e)); }
  };
  const apply = async () => {
    if (!cat) return setErr("Escolha a categoria.");
    try {
      setErr(null);
      const r = await api.post<{ categorizados: number; regra: unknown; impacto: Impact | null }>("/api/transactions/bulk-categorize", {
        descricao_normalizada: g.descricao_normalizada, categoria_id: cat,
        criar_regra: learn ? { padrao: kw, tipo_match: tipo, aplicar_retroativamente: retro } : undefined,
      });
      onDone(`${r.categorizados} movimento(s) categorizado(s)${r.regra ? ` · regra «${kw}» criada` : ""}${r.impacto?.conflitos ? ` · atenção: a regra também apanha ${r.impacto.conflitos} já categorizado(s) com outra categoria` : ""}`);
    } catch (e) { setErr(errorMessage(e)); }
  };
  return (
    <div className="card group" onKeyDown={(e) => { if (e.key === "Enter" && (e.target as HTMLElement).tagName === "INPUT") { e.preventDefault(); void apply(); } }}>
      <div className="group-head">
        <strong>{g.descricao_normalizada}</strong>
        <span className="muted">{g.n} movimento{g.n > 1 ? "s" : ""} · {eur(g.total)}</span>
      </div>
      <div className="muted small" title="Descrição original de um dos movimentos">{g.exemplo_original}</div>
      <div className="row">
        <CategorySelect aria-label="Categoria" categories={cats} value={cat} onChange={setCat} emptyLabel="Escolher categoria…" />
        <label className="check"><input type="checkbox" checked={learn} onChange={(e) => setLearn(e.target.checked)} /> Criar regra</label>
        {learn && (
          <>
            <input aria-label="Palavra-chave" value={kw} onChange={(e) => { setKw(e.target.value); setImpact(null); }} />
            <select aria-label="Tipo de correspondência" value={tipo} onChange={(e) => setTipo(e.target.value as "contem" | "comeca_por")}>
              <option value="contem">contém</option><option value="comeca_por">começa por</option>
            </select>
          </>
        )}
        <button className="primary" onClick={apply}>Categorizar</button>
      </div>
      {learn && (
        <div className="row small">
          <label className="check"><input type="checkbox" checked={retro} onChange={(e) => setRetro(e.target.checked)} /> Aplicar também aos movimentos existentes</label>
          <button className="link" onClick={preview}>Ver impacto da regra</button>
        </div>
      )}
      {impact && <p className={impact.conflitos ? "warn-text" : "muted"}>A regra afetaria {impact.afetados} movimento(s) ainda não manuais{impact.conflitos ? `, ${impact.conflitos} deles já com outra categoria` : ""}.</p>}
      {err && <p className="error" role="alert">{err}</p>}
    </div>
  );
}

export default function Review() {
  const cats = useAsync(() => api.get<Category[]>("/api/categories"), []);
  const groups = useAsync(() => api.get<{ total: number; grupos: Group[] }>("/api/transactions/uncategorized", { group_by: "description" }), []);
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <>
      <div className="toolbar"><h1>Por categorizar</h1>{groups.data && <span className="badge">{groups.data.total} movimentos · {groups.data.grupos.length} grupos</span>}</div>
      {msg && <p className="ok" role="status">{msg}</p>}
      {groups.error && <p className="error">{groups.error}</p>}
      {groups.data?.grupos.length === 0 && <p className="card muted">Tudo categorizado. 🎉</p>}
      {cats.data && groups.data?.grupos.map((g) => (
        <GroupRow key={g.descricao_normalizada} g={g} cats={cats.data!} onDone={(m) => { setMsg(m); groups.reload(); }} />
      ))}
    </>
  );
}
