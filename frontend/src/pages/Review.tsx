import { useEffect, useState } from "react";
import { api, errorMessage, type Category } from "../api";
import CategorySelect from "../components/CategorySelect";
import { useAsync } from "../hooks";
import { dataPt, eur } from "../lib/format";

type Group = { descricao_normalizada: string; n: number; total: string; exemplo_original: string; keyword_sugerida: string };
type ImpactLine = { id: number; data_movimento: string; descricao_original: string; descricao_normalizada: string; montante: string; categoria_atual: string | null; conflito: boolean };
type Impact = { afetados: number; conflitos: number; linhas?: ImpactLine[]; truncado?: boolean };
type Changed = {
  id: number; data_movimento: string; descricao_original: string; montante: string; categoria_id: number | null; categoria_nome: string | null; do_grupo: boolean;
  anterior: { categoria_id: number | null; categoria_origem: string | null; regra_id: number | null };
};
type BulkResult = { categorizados: number; aplicados: number; regra: { id: number } | null; impacto: Impact | null; alteradas: Changed[] };
export type LastAction = { msg: string; alteradas: Changed[]; regraId: number | null };

function GroupRow({ g, cats, onDone }: { g: Group; cats: Category[]; onDone: (a: LastAction) => void }) {
  const [cat, setCat] = useState<number | null>(null);
  const [kw, setKw] = useState(g.keyword_sugerida);
  const [tipo, setTipo] = useState<"contem" | "comeca_por">("contem");
  const [learn, setLearn] = useState(true);
  const [retro, setRetro] = useState(true); // por omissão a regra aplica-se a todas as linhas já importadas
  const [impact, setImpact] = useState<Impact | null>(null);
  const [excluded, setExcluded] = useState<Set<number>>(new Set());
  const [err, setErr] = useState<string | null>(null);

  // As linhas afetadas calculam-se sozinhas e atualizam quando se muda a palavra-chave: vê-se o que vai acontecer antes de clicar.
  useEffect(() => {
    if (!learn || !cat || kw.trim().length < 2) { setImpact(null); return; }
    let alive = true;
    const t = setTimeout(() => {
      api.post<Impact>("/api/rules/preview-impact?linhas=300", { padrao: kw, tipo_match: tipo, categoria_id: cat })
        .then((i) => alive && setImpact(i))
        .catch(() => alive && setImpact(null));
    }, 300);
    return () => { alive = false; clearTimeout(t); };
  }, [learn, cat, kw, tipo]);

  const all = impact?.linhas ?? [];
  const visible = retro ? all : all.filter((l) => l.descricao_normalizada === g.descricao_normalizada);
  const hidden = retro && impact ? Math.max(impact.afetados - all.length, 0) : 0; // além das 300 mostradas
  const marked = visible.filter((l) => !excluded.has(l.id));
  const total = impact ? marked.length + hidden : g.n;
  const toggle = (id: number) => setExcluded((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  const apply = async () => {
    if (!cat) return setErr("Escolha a categoria.");
    try {
      setErr(null);
      const r = await api.post<BulkResult>("/api/transactions/bulk-categorize", {
        descricao_normalizada: g.descricao_normalizada, categoria_id: cat,
        criar_regra: learn ? { padrao: kw, tipo_match: tipo, aplicar_retroativamente: retro } : undefined,
        excluir_ids: visible.filter((l) => excluded.has(l.id)).map((l) => l.id),
      });
      const extra = r.aplicados ? ` + ${r.aplicados} de outras descrições` : "";
      onDone({
        msg: `${r.categorizados} movimento(s) categorizado(s)${extra}${r.regra ? ` · regra «${kw}» criada (aplica-se também aos próximos extratos)` : ""}`,
        alteradas: r.alteradas, regraId: r.regra?.id ?? null,
      });
    } catch (e) { setErr(errorMessage(e)); }
  };
  return (
    <div className="card group" onKeyDown={(e) => { if (e.key === "Enter" && (e.target as HTMLElement).tagName === "INPUT" && (e.target as HTMLInputElement).type !== "checkbox") { e.preventDefault(); void apply(); } }}>
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
            <input aria-label="Palavra-chave" value={kw} onChange={(e) => setKw(e.target.value)} />
            <select aria-label="Tipo de correspondência" value={tipo} onChange={(e) => setTipo(e.target.value as "contem" | "comeca_por")}>
              <option value="contem">contém</option><option value="comeca_por">começa por</option>
            </select>
          </>
        )}
        <button className="primary" onClick={apply}>{total > 1 ? `Categorizar ${total} linhas` : "Categorizar"}</button>
      </div>
      {learn && (
        <div className="row small">
          <label className="check"><input type="checkbox" checked={retro} onChange={(e) => setRetro(e.target.checked)} /> Aplicar a todas as linhas já importadas com «{kw}»</label>
          {impact && impact.conflitos > 0 && retro && <span className="warn-text">{impact.conflitos} já têm outra categoria (de regra) e serão alteradas</span>}
        </div>
      )}
      {learn && impact && visible.length > 0 && (
        <details className="lines" open>
          <summary>Linhas que vão ser categorizadas ({marked.length}{hidden ? ` + ${hidden} não listadas` : ""}) · desmarque as que não pertencem</summary>
          <div className="lines-scroll">
            <table className="data">
              <thead><tr><th /><th>Data</th><th>Descrição</th><th className="num">Montante</th><th>Categoria atual</th></tr></thead>
              <tbody>
                {visible.map((l) => (
                  <tr key={l.id} className={excluded.has(l.id) ? "muted struck" : ""}>
                    <td><input type="checkbox" aria-label={`Incluir ${l.descricao_original}`} checked={!excluded.has(l.id)} onChange={() => toggle(l.id)} /></td>
                    <td>{dataPt(l.data_movimento)}</td><td title={l.descricao_original}>{l.descricao_original}</td>
                    <td className="num">{eur(l.montante)}</td>
                    <td>{l.categoria_atual ? <span className={l.conflito ? "warn-text" : "muted"}>{l.categoria_atual}{l.conflito ? " → será alterada" : ""}</span> : <span className="muted">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {impact.truncado && <p className="muted small">A mostrar as primeiras {all.length} de {impact.afetados}. As restantes também serão categorizadas; as desmarcações só valem para as linhas listadas.</p>}
          {excluded.size > 0 && <p className="muted small">As linhas desmarcadas ficam por categorizar. A regra continuará a aplicar-se a extratos futuros: se for demasiado ampla, torne a palavra-chave mais específica.</p>}
        </details>
      )}
      {err && <p className="error" role="alert">{err}</p>}
    </div>
  );
}

/** Última ação: mostra o que mudou, deixa corrigir linha a linha e desfazer tudo (inclui apagar a regra criada). */
function LastActionCard({ last, cats, onUndo, onClose, onCorrected }: {
  last: LastAction; cats: Category[]; onUndo: () => void; onClose: () => void; onCorrected: (id: number, cat: number | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const correct = async (id: number, c: number | null) => {
    try { setErr(null); await api.patch(`/api/transactions/${id}`, { categoria_id: c }); onCorrected(id, c); }
    catch (e) { setErr(errorMessage(e)); }
  };
  return (
    <div className="card last" role="status">
      <div className="row">
        <strong className="ok">{last.msg}</strong>
        <button onClick={onUndo}>Desfazer tudo</button>
        <button className="link" onClick={() => setOpen(!open)}>{open ? "Esconder" : "Ver e corrigir"} as {last.alteradas.length} linhas alteradas</button>
        <button className="link" onClick={onClose} aria-label="Fechar">✕</button>
      </div>
      {err && <p className="error" role="alert">{err}</p>}
      {open && (
        <div className="lines-scroll">
          <table className="data">
            <thead><tr><th>Data</th><th>Descrição</th><th className="num">Montante</th><th>Categoria</th></tr></thead>
            <tbody>
              {last.alteradas.map((a) => (
                <tr key={a.id}>
                  <td>{dataPt(a.data_movimento)}</td>
                  <td title={a.descricao_original}>{a.descricao_original}{!a.do_grupo && <span className="tag">outra descrição</span>}</td>
                  <td className="num">{eur(a.montante)}</td>
                  <td><CategorySelect aria-label={`Categoria de ${a.descricao_original}`} categories={cats} value={a.categoria_id} onChange={(c) => correct(a.id, c)} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function Review() {
  const cats = useAsync(() => api.get<Category[]>("/api/categories"), []);
  const groups = useAsync(() => api.get<{ total: number; grupos: Group[] }>("/api/transactions/uncategorized", { group_by: "description" }), []);
  const [last, setLast] = useState<LastAction | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const undo = async () => {
    if (!last) return;
    try {
      setErr(null);
      await api.post("/api/transactions/restore", { itens: last.alteradas.map((a) => ({ id: a.id, ...a.anterior })), apagar_regra_id: last.regraId });
      setLast(null);
      setMsg("Ação desfeita: as linhas voltaram ao estado anterior e a regra criada foi apagada.");
      groups.reload();
    } catch (e) { setErr(errorMessage(e)); }
  };
  return (
    <>
      <div className="toolbar"><h1>Por categorizar</h1>{groups.data && <span className="badge">{groups.data.total} movimentos · {groups.data.grupos.length} grupos</span>}</div>
      <div className="sticky-top">
        {last && cats.data && (
          <LastActionCard last={last} cats={cats.data} onUndo={undo} onClose={() => setLast(null)}
            onCorrected={(id, c) => setLast({ ...last, alteradas: last.alteradas.map((a) => (a.id === id ? { ...a, categoria_id: c } : a)) })} />
        )}
        {msg && !last && <p className="ok sticky" role="status">{msg}</p>}
        {err && <p className="error" role="alert">{err}</p>}
      </div>
      {groups.error && <p className="error">{groups.error}</p>}
      {groups.data?.grupos.length === 0 && <p className="card muted">Tudo categorizado. 🎉</p>}
      {cats.data && groups.data?.grupos.map((g) => (
        <GroupRow key={g.descricao_normalizada} g={g} cats={cats.data!} onDone={(a) => { setLast(a); setMsg(null); groups.reload(); }} />
      ))}
    </>
  );
}
