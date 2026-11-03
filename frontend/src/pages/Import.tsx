import { useRef, useState, type DragEvent } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage, type Account } from "../api";
import { CoverageSummary } from "../components/Coverage";
import { useAsync } from "../hooks";
import { dataPt, eur } from "../lib/format";

type Line = { i: number; data_movimento: string; descricao_original: string; montante: string; saldo_apos: string | null; estado: "novo" | "duplicado" | "possivel_duplicado" };
type Preview = {
  id: number; conta_id: number; estado: string; reconciliado: boolean; diferenca: string; saldo_inicial: string; saldo_final: string;
  periodo_inicio: string; periodo_fim: string; ordem_ficheiro: string; avisos: string[]; linhas: Line[];
  resumo: { novo: number; duplicado: number; possivel_duplicado: number };
};
type Done = { n_movimentos: number; n_duplicados_ignorados: number; n_excluidos_utilizador: number };
type ImportRow = { id: number; ficheiro_nome: string; estado: string; periodo_inicio: string; periodo_fim: string; n_movimentos: number; n_duplicados_ignorados: number };
type Correction = { montante?: string; saldo_apos?: string };

const ESTADO: Record<Line["estado"], string> = { novo: "novo", duplicado: "duplicado", possivel_duplicado: "possível duplicado" };

export default function Import() {
  const accounts = useAsync(() => api.get<Account[]>("/api/accounts"), []);
  const history = useAsync(() => api.get<ImportRow[]>("/api/imports"), []);
  const [contaId, setContaId] = useState<number | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [excluded, setExcluded] = useState<Set<number>>(new Set());
  const [include, setInclude] = useState<Set<number>>(new Set());
  const [fixes, setFixes] = useState<Record<number, Correction>>({});
  const [done, setDone] = useState<Done | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const conta = contaId ?? accounts.data?.[0]?.id ?? null;

  const wrap = async (fn: () => Promise<void>) => {
    setBusy(true); setErr(null);
    try { await fn(); } catch (e) { setErr(errorMessage(e)); } finally { setBusy(false); }
  };
  const createAccount = () => wrap(async () => {
    await api.post("/api/accounts", { nome: "Bankinter Ordenado", banco: "Bankinter", parser_id: "bankinter" });
    accounts.reload();
  });
  const upload = (file: File) => wrap(async () => {
    if (!conta) throw new Error("Crie primeiro uma conta.");
    const fd = new FormData();
    fd.append("conta_id", String(conta)); fd.append("file", file);
    setDone(null); setExcluded(new Set()); setInclude(new Set()); setFixes({});
    setPreview(await api.post<Preview>("/api/imports/preview", fd));
    history.reload();
  });
  const onDrop = (e: DragEvent) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) void upload(f); };
  const toggle = (set: Set<number>, setter: (s: Set<number>) => void, i: number) => { const n = new Set(set); if (n.has(i)) n.delete(i); else n.add(i); setter(n); };
  const confirmImport = () => wrap(async () => {
    if (!preview) return;
    const correcoes = Object.fromEntries(Object.entries(fixes).filter(([, c]) => c.montante || c.saldo_apos));
    try {
      setDone(await api.post<Done>(`/api/imports/${preview.id}/confirm`, { linhas_excluidas: [...excluded], correcoes, incluir_possiveis_duplicados: [...include] }));
      setPreview(null); history.reload();
    } catch (e) {
      // sem reconciliação o servidor devolve a diferença e a importação continua em pré-visualização
      setPreview(await api.get<Preview>(`/api/imports/${preview.id}`).catch(() => preview));
      throw e;
    }
  });
  const cancel = () => wrap(async () => { if (preview) await api.del(`/api/imports/${preview.id}`); setPreview(null); history.reload(); });
  const revert = (r: ImportRow) => {
    if (!confirm(`Reverter «${r.ficheiro_nome}»? Os ${r.n_movimentos} movimentos serão apagados e as categorizações manuais perdem-se.`)) return;
    void wrap(async () => { await api.del(`/api/imports/${r.id}`); history.reload(); });
  };

  return (
    <>
      <div className="toolbar"><h1>Importar extrato</h1></div>
      {err && <p className="error" role="alert">{err}</p>}
      {accounts.data?.length === 0 && (
        <div className="card"><p>Ainda não tem nenhuma conta.</p><button className="primary" onClick={createAccount}>Criar conta «Bankinter Ordenado»</button></div>
      )}
      {!preview && accounts.data && accounts.data.length > 0 && (
        <div className="card drop" onDragOver={(e) => e.preventDefault()} onDrop={onDrop}>
          {accounts.data.length > 1 && (
            <select value={conta ?? ""} onChange={(e) => setContaId(Number(e.target.value))} aria-label="Conta">
              {accounts.data.map((a) => <option key={a.id} value={a.id}>{a.nome}</option>)}
            </select>
          )}
          <p>Largue aqui o ficheiro <strong>.xls</strong> exportado do homebanking (sem o abrir noutra aplicação), ou</p>
          <button className="primary" disabled={busy} onClick={() => fileRef.current?.click()}>{busy ? "A processar…" : "Escolher ficheiro"}</button>
          <input ref={fileRef} type="file" accept=".xls,application/vnd.ms-excel,.csv,text/csv" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); e.target.value = ""; }} />
        </div>
      )}
      {done && (
        <div className="card ok" role="status">
          <strong>Importação concluída:</strong> {done.n_movimentos} movimentos gravados, {done.n_duplicados_ignorados} duplicados ignorados, {done.n_excluidos_utilizador} excluídos por si.{" "}
          <Link to="/rever">Categorizar agora →</Link>
        </div>
      )}
      {preview && (
        <>
          <div className="card">
            <div className="summary">
              <span className={`badge ${preview.reconciliado ? "good" : "bad"}`}>{preview.reconciliado ? "✓ Saldos reconciliam" : `✗ Não reconcilia (diferença ${eur(preview.diferenca)})`}</span>
              <span>{dataPt(preview.periodo_inicio)} – {dataPt(preview.periodo_fim)}</span>
              <span>Saldo inicial {eur(preview.saldo_inicial)} → final {eur(preview.saldo_final)}</span>
              <span>{preview.resumo.novo} novos · {preview.resumo.duplicado} duplicados · {preview.resumo.possivel_duplicado} possíveis duplicados</span>
            </div>
            {preview.avisos.map((a) => <p key={a} className="warn-text">⚠ {a}</p>)}
            {!preview.reconciliado && <p className="muted">Corrija o montante ou o saldo das linhas em causa (ícone ✎) e confirme de novo; o servidor volta a reconciliar tudo.</p>}
          </div>
          <div className="card flush">
            <table className="data">
              <thead><tr><th>Data</th><th>Descrição</th><th className="num">Montante</th><th className="num">Saldo</th><th>Estado</th><th>Excluir</th><th>Gravar mesmo assim</th><th /></tr></thead>
              <tbody>
                {preview.linhas.map((l) => (
                  <tr key={l.i} className={l.estado !== "novo" || excluded.has(l.i) ? "muted" : ""}>
                    <td>{dataPt(l.data_movimento)}</td><td>{l.descricao_original}</td>
                    <td className="num">{fixes[l.i]?.montante !== undefined ? <input className="mini" aria-label="Montante" defaultValue={l.montante} onChange={(e) => setFixes({ ...fixes, [l.i]: { ...fixes[l.i], montante: e.target.value } })} /> : eur(l.montante)}</td>
                    <td className="num">{fixes[l.i]?.saldo_apos !== undefined ? <input className="mini" aria-label="Saldo" defaultValue={l.saldo_apos ?? ""} onChange={(e) => setFixes({ ...fixes, [l.i]: { ...fixes[l.i], saldo_apos: e.target.value } })} /> : eur(l.saldo_apos)}</td>
                    <td><span className={`tag ${l.estado}`}>{ESTADO[l.estado]}</span></td>
                    <td><input type="checkbox" aria-label={`Excluir linha ${l.i + 1}`} checked={excluded.has(l.i)} onChange={() => toggle(excluded, setExcluded, l.i)} /></td>
                    <td>{l.estado === "possivel_duplicado" && <input type="checkbox" aria-label={`Gravar linha ${l.i + 1} mesmo assim`} checked={include.has(l.i)} onChange={() => toggle(include, setInclude, l.i)} />}</td>
                    <td><button className="link" title="Corrigir montante/saldo" aria-label={`Corrigir linha ${l.i + 1}`} onClick={() => setFixes({ ...fixes, [l.i]: fixes[l.i] ?? { montante: l.montante, saldo_apos: l.saldo_apos ?? "" } })}>✎</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="row">
            <button className="primary" disabled={busy} onClick={confirmImport}>Confirmar importação</button>
            <button disabled={busy} onClick={cancel}>Cancelar</button>
          </div>
        </>
      )}
      <CoverageSummary />
      <h2>Importações anteriores</h2>
      <div className="card flush">
        <table className="data">
          <thead><tr><th>Ficheiro</th><th>Período</th><th>Estado</th><th className="num">Movimentos</th><th className="num">Duplicados</th><th /></tr></thead>
          <tbody>
            {history.data?.map((r) => (
              <tr key={r.id}>
                <td>{r.ficheiro_nome}</td><td>{dataPt(r.periodo_inicio)} – {dataPt(r.periodo_fim)}</td><td>{r.estado}</td>
                <td className="num">{r.n_movimentos}</td><td className="num">{r.n_duplicados_ignorados}</td>
                <td>{r.estado === "confirmada" && <button className="link danger" onClick={() => revert(r)}>Reverter</button>}</td>
              </tr>
            ))}
            {history.data?.length === 0 && <tr><td colSpan={6} className="muted">Sem importações.</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  );
}
