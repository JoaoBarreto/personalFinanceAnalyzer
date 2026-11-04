import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, errorMessage, type Account } from "../api";
import { useAsync } from "../hooks";

type Bank = { parser_id: string; banco: string; formatos: string[] };
const OUTRO = "__outro__";

/** Assistente «Adicionar conta»: banco → nome → (extrato). Bancos sem parser: conta «pendente» + estrutura mascarada. */
function AddAccount({ banks, onCreated }: { banks: Bank[]; onCreated: () => void }) {
  const nav = useNavigate();
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [bank, setBank] = useState<string>(banks[0]?.parser_id ?? OUTRO);
  const [outroNome, setOutroNome] = useState("");
  const [nome, setNome] = useState("");
  const [created, setCreated] = useState<Account | null>(null);
  const [estrutura, setEstrutura] = useState<string | null>(null);
  const [rotulos, setRotulos] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const suportado = bank !== OUTRO;
  const bancoNome = suportado ? banks.find((b) => b.parser_id === bank)?.banco ?? bank : outroNome.trim();

  const run = async (fn: () => Promise<void>) => {
    setBusy(true); setErr(null);
    try { await fn(); } catch (e) { setErr(errorMessage(e)); } finally { setBusy(false); }
  };
  const criar = () => run(async () => {
    const c = await api.post<Account>("/api/accounts", { nome: nome.trim(), banco: bancoNome, parser_id: suportado ? bank : "pendente" });
    setCreated(c); onCreated(); setStep(3);
  });
  const analisar = (file: File) => run(async () => {
    const fd = new FormData();
    fd.append("file", file); fd.append("mostrar_rotulos", String(rotulos));
    setEstrutura((await api.post<{ estrutura: string }>("/api/banks/structure", fd)).estrutura);
  });
  const copiar = async () => {
    if (estrutura) { await navigator.clipboard.writeText(estrutura); setCopied(true); setTimeout(() => setCopied(false), 2000); }
  };
  const recomecar = () => { setStep(1); setCreated(null); setEstrutura(null); setNome(""); setOutroNome(""); setErr(null); };

  return (
    <section className="card wizard" aria-label="Adicionar conta">
      <h2>Adicionar conta</h2>
      <ol className="steps" aria-label="Passos">
        {["Banco", "Nome da conta", suportado ? "Extrato" : "Formato do extrato"].map((s, i) => (
          <li key={s} className={step === i + 1 ? "on" : step > i + 1 ? "done" : ""} aria-current={step === i + 1 ? "step" : undefined}>{s}</li>
        ))}
      </ol>
      {err && <p className="error" role="alert">{err}</p>}
      {step === 1 && (
        <div className="stack">
          <label>Banco
            <select value={bank} onChange={(e) => setBank(e.target.value)}>
              {banks.map((b) => <option key={b.parser_id} value={b.parser_id}>{b.banco}</option>)}
              <option value={OUTRO}>Outro banco (ainda não suportado)…</option>
            </select>
          </label>
          {suportado
            ? <p className="muted small">Formatos aceites: {banks.find((b) => b.parser_id === bank)?.formatos.join(", ")}. Use o ficheiro original do homebanking, sem o guardar noutra aplicação.</p>
            : <>
                <label>Nome do banco<input value={outroNome} onChange={(e) => setOutroNome(e.target.value)} placeholder="ex.: o seu banco" /></label>
                <p className="muted small">A conta fica criada, mas só importa extratos quando o banco tiver suporte. No passo 3 pode ver a estrutura do seu extrato com os valores mascarados, para pedir esse suporte sem partilhar dados pessoais.</p>
              </>}
          <div className="row"><button className="primary" disabled={!suportado && !outroNome.trim()} onClick={() => setStep(2)}>Continuar</button></div>
        </div>
      )}
      {step === 2 && (
        <form className="stack" onSubmit={(e) => { e.preventDefault(); void criar(); }}>
          <label>Nome da conta<input value={nome} onChange={(e) => setNome(e.target.value)} placeholder="ex.: Ordenado" required autoFocus /></label>
          <p className="muted small">Banco: <strong>{bancoNome}</strong>. A conta é só sua: mais ninguém a vê.</p>
          <div className="row"><button type="button" className="link" onClick={() => setStep(1)}>‹ Voltar</button><button className="primary" disabled={busy || !nome.trim()}>Criar conta</button></div>
        </form>
      )}
      {step === 3 && created && suportado && (
        <div className="stack">
          <p className="ok">✓ Conta «{created.nome}» criada.</p>
          <p>Passo seguinte: carregar o extrato (pré-visualização antes de gravar) e depois categorizar.</p>
          <div className="row"><button className="primary" onClick={() => nav(`/importar?conta=${created.id}`)}>Importar extrato</button><button className="link" onClick={recomecar}>Adicionar outra conta</button></div>
        </div>
      )}
      {step === 3 && created && !suportado && (
        <div className="stack">
          <p className="ok">✓ Conta «{created.nome}» criada (banco por suportar).</p>
          <p>Ainda não é possível importar extratos de <strong>{bancoNome}</strong>. Carregue um extrato real para ver só o <em>formato</em> (letras viram «x» e dígitos «9»; nada é gravado) e envie esse texto a quem mantém a aplicação para pedir o suporte.</p>
          <label className="check"><input type="checkbox" checked={rotulos} onChange={(e) => setRotulos(e.target.checked)} /> Mostrar nomes de colunas e rótulos sem máscara (confirme primeiro que o cabeçalho do extrato não tem dados pessoais)</label>
          <div className="row">
            <input ref={fileRef} type="file" accept=".xls,.xlsx,.csv,.txt" aria-label="Extrato" onChange={(e) => { const f = e.target.files?.[0]; if (f) void analisar(f); }} />
            {busy && <span className="muted">A analisar…</span>}
          </div>
          {estrutura && (
            <>
              <pre className="mask-out" tabIndex={0} aria-label="Estrutura mascarada">{estrutura}</pre>
              <div className="row"><button className="primary" onClick={() => void copiar()}>{copied ? "Copiado ✓" : "Copiar"}</button><span className="muted small">Reveja antes de partilhar.</span></div>
            </>
          )}
          <div className="row"><button className="link" onClick={recomecar}>Adicionar outra conta</button></div>
        </div>
      )}
    </section>
  );
}

export default function Accounts() {
  const accounts = useAsync(() => api.get<Account[]>("/api/accounts"), []);
  const banks = useAsync(() => api.get<Bank[]>("/api/banks"), []);
  const [err, setErr] = useState<string | null>(null);
  const wrap = async (fn: () => Promise<void>) => {
    try { setErr(null); await fn(); } catch (e) { setErr(errorMessage(e)); }
  };
  const pendentes = accounts.data?.filter((a) => a.parser_id === "pendente") ?? [];
  return (
    <>
      <div className="toolbar"><h1>Contas</h1></div>
      {err && <p className="error" role="alert">{err}</p>}
      {banks.data && <AddAccount banks={banks.data} onCreated={accounts.reload} />}
      <div className="card flush">
        <table className="data">
          <thead><tr><th>Nome</th><th>Banco</th><th>Estado</th><th></th></tr></thead>
          <tbody>
            {accounts.data?.map((a) => (
              <tr key={a.id} className={a.arquivada ? "muted" : ""}>
                <td>{a.nome}</td>
                <td>{a.banco}{a.parser_id === "pendente" && <span className="tag" title="Ainda não há parser para este banco">por suportar</span>}</td>
                <td>
                  <button className="link" onClick={() => wrap(async () => { await api.patch(`/api/accounts/${a.id}`, { arquivada: !a.arquivada }); accounts.reload(); })}>
                    {a.arquivada ? "Arquivada · reativar" : "Ativa · arquivar"}
                  </button>
                </td>
                <td>{a.parser_id !== "pendente" && !a.arquivada && <Link to={`/importar?conta=${a.id}`}>Importar</Link>}</td>
              </tr>
            ))}
            {accounts.data?.length === 0 && <tr><td colSpan={4} className="muted">Ainda não tem contas: use «Adicionar conta» acima.</td></tr>}
          </tbody>
        </table>
      </div>
      {pendentes.length > 0 && banks.data && (
        <p className="muted small">Quando o banco de uma conta «por suportar» passar a ter suporte, mude-a para o respetivo banco:{" "}
          {pendentes.map((a) => (
            <span key={a.id}>{a.nome}: <select aria-label={`Banco suportado para ${a.nome}`} defaultValue="" onChange={(e) => e.target.value && wrap(async () => { await api.patch(`/api/accounts/${a.id}`, { parser_id: e.target.value }); accounts.reload(); })}>
              <option value="">—</option>{banks.data!.map((b) => <option key={b.parser_id} value={b.parser_id}>{b.banco}</option>)}</select>{" "}</span>
          ))}
        </p>
      )}
      <p className="muted small">As contas são só suas: mais ninguém as vê. Os utilizadores criam-se no servidor com <code>python -m app.cli create-user</code>.</p>
    </>
  );
}
