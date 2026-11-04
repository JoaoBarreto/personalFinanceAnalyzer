import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, errorMessage, type Account } from "../api";
import { useAsync } from "../hooks";
import { dataPt, eur } from "../lib/format";

type Bank = { parser_id: string; banco: string; formatos: string[] };
type Question = { id: string; texto: string; opcoes: { valor: string | number; rotulo: string }[] };
type Sample = { bruto: Record<string, string>; lido: { data: string; descricao: string; montante: string; saldo: string } };
type Proposal = {
  ok: boolean; modelo: Record<string, string | string[] | boolean | null> | null; perguntas: Question[]; amostra: Sample[];
  resumo?: { movimentos: number; periodo: string[]; ordem: string; saldo_inicial: string; saldo_final: string };
  motivo: string | null; colunas?: string[];
};
const OUTRO = "__outro__";
const MILHARES_TXT: Record<string, string> = { nenhum: "sem separador de milhares", ponto: "ponto nos milhares", virgula: "vírgula nos milhares", espaco: "espaço nos milhares" };

/** Assistente «Adicionar conta»: banco → nome → extrato. Para outro banco o extrato define o modelo (detetado e confirmado). */
function AddAccount({ banks, onCreated }: { banks: Bank[]; onCreated: () => void }) {
  const nav = useNavigate();
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);
  const [bank, setBank] = useState<string>(banks[0]?.parser_id ?? OUTRO);
  const [outroNome, setOutroNome] = useState("");
  const [nome, setNome] = useState("");
  const [created, setCreated] = useState<Account | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [proposta, setProposta] = useState<Proposal | null>(null);
  const [respostas, setRespostas] = useState<Record<string, string | number>>({});
  const [confirmo, setConfirmo] = useState(false);
  const [estrutura, setEstrutura] = useState<string | null>(null);
  const [rotulos, setRotulos] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const suportado = bank !== OUTRO;
  const bancoNome = suportado ? banks.find((b) => b.parser_id === bank)?.banco ?? bank : outroNome.trim();

  const run = async (fn: () => Promise<void>) => {
    setBusy(true); setErr(null);
    try { await fn(); } catch (e) { setErr(errorMessage(e)); } finally { setBusy(false); }
  };
  const criarSuportada = () => run(async () => {
    const c = await api.post<Account>("/api/accounts", { nome: nome.trim(), banco: bancoNome, parser_id: bank });
    setCreated(c); onCreated(); setStep(4);
  });
  const detetar = (f: File, resp: Record<string, string | number>) => run(async () => {
    const fd = new FormData();
    fd.append("file", f); fd.append("respostas", JSON.stringify(resp));
    setFile(f); setConfirmo(false); setProposta(await api.post<Proposal>("/api/banks/detect", fd));
  });
  const reverificar = (modelo: Record<string, unknown>) => run(async () => {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file); fd.append("modelo", JSON.stringify(modelo));
    const r = await api.post<Proposal>("/api/banks/verify", fd);
    setConfirmo(false); setProposta({ ...r, colunas: proposta?.colunas });
  });
  const criarEImportar = () => run(async () => {
    if (!proposta?.modelo || !file) return;
    const c = await api.post<Account>("/api/accounts", { nome: nome.trim(), banco: bancoNome, parser_id: "generico", config_importacao: proposta.modelo });
    onCreated();
    const fd = new FormData();
    fd.append("conta_id", String(c.id)); fd.append("file", file);
    try {
      const pre = await api.post<{ id: number }>("/api/imports/preview", fd);
      nav(`/importar?preview=${pre.id}`);
    } catch (e) {
      setCreated(c); setErr(`Conta criada, mas a importação foi recusada: ${errorMessage(e)}`); setStep(4);
    }
  });
  const criarPendente = () => run(async () => {
    const c = await api.post<Account>("/api/accounts", { nome: nome.trim(), banco: bancoNome, parser_id: "pendente" });
    setCreated(c); onCreated(); setStep(4);
  });
  const analisar = (f: File) => run(async () => {
    const fd = new FormData();
    fd.append("file", f); fd.append("mostrar_rotulos", String(rotulos));
    setEstrutura((await api.post<{ estrutura: string }>("/api/banks/structure", fd)).estrutura);
  });
  const copiar = async () => {
    if (estrutura) { await navigator.clipboard.writeText(estrutura); setCopied(true); setTimeout(() => setCopied(false), 2000); }
  };
  const recomecar = () => { setStep(1); setCreated(null); setFile(null); setProposta(null); setRespostas({}); setEstrutura(null); setNome(""); setOutroNome(""); setErr(null); };
  const m = proposta?.modelo;
  const colMontante = m ? (m.montante as string | null) : null;

  return (
    <section className="card wizard" aria-label="Adicionar conta">
      <h2>Adicionar conta</h2>
      <ol className="steps" aria-label="Passos">
        {["Banco", "Nome da conta", "Extrato"].map((s, i) => (
          <li key={s} className={Math.min(step, 3) === i + 1 ? "on" : step > i + 1 ? "done" : ""} aria-current={Math.min(step, 3) === i + 1 ? "step" : undefined}>{s}</li>
        ))}
      </ol>
      {err && <p className="error" role="alert">{err}</p>}
      {step === 1 && (
        <div className="stack">
          <label>Banco
            <select value={bank} onChange={(e) => setBank(e.target.value)}>
              {banks.map((b) => <option key={b.parser_id} value={b.parser_id}>{b.banco}</option>)}
              <option value={OUTRO}>Outro banco…</option>
            </select>
          </label>
          {suportado
            ? <p className="muted small">Formatos aceites: {banks.find((b) => b.parser_id === bank)?.formatos.join(", ")}. Use o ficheiro original do homebanking, sem o guardar noutra aplicação.</p>
            : <>
                <label>Nome do banco<input value={outroNome} onChange={(e) => setOutroNome(e.target.value)} placeholder="ex.: o seu banco" /></label>
                <p className="muted small">Para um banco novo basta carregar o extrato (.xls, .xlsx ou .csv, com coluna de saldo): a aplicação percebe o formato e pede-lhe para confirmar com exemplos.</p>
              </>}
          <div className="row"><button className="primary" disabled={!suportado && !outroNome.trim()} onClick={() => setStep(2)}>Continuar</button></div>
        </div>
      )}
      {step === 2 && (
        <form className="stack" onSubmit={(e) => { e.preventDefault(); if (suportado) void criarSuportada(); else setStep(3); }}>
          <label>Nome da conta<input value={nome} onChange={(e) => setNome(e.target.value)} placeholder="ex.: Ordenado" required autoFocus /></label>
          <p className="muted small">Banco: <strong>{bancoNome}</strong>. A conta é só sua: mais ninguém a vê.</p>
          <div className="row"><button type="button" className="link" onClick={() => setStep(1)}>‹ Voltar</button><button className="primary" disabled={busy || !nome.trim()}>{suportado ? "Criar conta" : "Continuar"}</button></div>
        </form>
      )}
      {step === 3 && !suportado && (
        <div className="stack">
          {!proposta && (
            <>
              <p>Carregue o extrato de <strong>{bancoNome}</strong> (um ficheiro real, com vários movimentos). Nada é gravado até confirmar.</p>
              <div className="row">
                <input type="file" accept=".xls,.xlsx,.csv,.txt" aria-label="Extrato" onChange={(e) => { const f = e.target.files?.[0]; if (f) void detetar(f, {}); }} />
                {busy && <span className="muted">A analisar…</span>}
              </div>
              <div className="row"><button type="button" className="link" onClick={() => setStep(2)}>‹ Voltar</button></div>
            </>
          )}
          {proposta && proposta.perguntas.length > 0 && (
            <form className="stack" onSubmit={(e) => { e.preventDefault(); if (file) void detetar(file, respostas); }}>
              {proposta.perguntas.map((q) => (
                <fieldset key={q.id} className="stack"><legend>{q.texto}</legend>
                  {q.opcoes.map((o) => (
                    <label key={String(o.valor)} className="check"><input type="radio" name={q.id} checked={respostas[q.id] === o.valor} onChange={() => setRespostas({ ...respostas, [q.id]: o.valor })} /> {o.rotulo}</label>
                  ))}
                </fieldset>
              ))}
              <div className="row"><button className="primary" disabled={busy || proposta.perguntas.some((q) => respostas[q.id] === undefined)}>Continuar</button></div>
            </form>
          )}
          {proposta && proposta.ok && m && (
            <>
              <h3>Confirme a leitura do extrato</h3>
              <p className="muted small">Comparei o texto original com o valor lido. Veja se «{proposta.amostra[0]?.bruto[(colMontante ?? (m.debito as string)) ?? ""]}» ficou {eur(proposta.amostra[0]?.lido.montante)}: se algum valor estiver errado, não confirme.</p>
              <table className="data sample">
                <thead><tr><th>Data (original)</th><th>Montante (original)</th><th>Saldo (original)</th><th>→ Data</th><th>→ Montante</th><th>→ Saldo</th><th>Descrição</th></tr></thead>
                <tbody>
                  {proposta.amostra.map((a, i) => (
                    <tr key={i}>
                      <td>{a.bruto[m.data as string]}</td>
                      <td>{colMontante ? a.bruto[colMontante] : `déb. ${a.bruto[m.debito as string] || "—"} / créd. ${a.bruto[m.credito as string] || "—"}`}</td>
                      <td>{a.bruto[m.saldo as string]}</td>
                      <td>{dataPt(a.lido.data)}</td><td className="num">{eur(a.lido.montante)}</td><td className="num">{eur(a.lido.saldo)}</td>
                      <td className="c-desc">{a.lido.descricao}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {proposta.resumo && <p className="small">{proposta.resumo.movimentos} movimentos de {dataPt(proposta.resumo.periodo[0])} a {dataPt(proposta.resumo.periodo[1])}; saldo de {eur(proposta.resumo.saldo_inicial)} a {eur(proposta.resumo.saldo_final)}. <span className="ok">✓ As contas fecham ao cêntimo.</span></p>}
              <p className="muted small">Formato: {String(m.formato).toUpperCase()}{m.formato === "csv" ? ` (${m.codificacao}, separador «${m.separador}»)` : ""}; datas {String(m.formato_data).replace("aaaa", "ano")}; decimal «{String(m.decimal)}», {MILHARES_TXT[String(m.milhares)]}.</p>
              {proposta.colunas && (
                <label>Coluna da descrição
                  <select value={(m.descricao as string[])[0]} onChange={(e) => void reverificar({ ...m, descricao: [e.target.value] })}>
                    {proposta.colunas.filter((c) => c).map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </label>
              )}
              <label className="check"><input type="checkbox" checked={confirmo} onChange={(e) => setConfirmo(e.target.checked)} /> Confirmo que as datas, os montantes e os saldos foram lidos corretamente.</label>
              <div className="row">
                <button className="primary" disabled={!confirmo || busy} onClick={() => void criarEImportar()}>Criar conta e ver a importação</button>
                <button className="link" onClick={() => { setProposta(null); setFile(null); }}>Escolher outro ficheiro</button>
              </div>
            </>
          )}
          {proposta && !proposta.ok && proposta.perguntas.length === 0 && (
            <>
              <p className="warn-text">Não consegui perceber este extrato com segurança.</p>
              <p className="error">{proposta.motivo}</p>
              <p className="muted small">Pode criar a conta mesmo assim (fica «por suportar») e ver a estrutura do ficheiro, com valores mascarados, para pedir suporte.</p>
              <div className="row">
                <button className="primary" disabled={busy} onClick={() => void criarPendente()}>Criar conta por suportar</button>
                <button className="link" onClick={() => { setProposta(null); setFile(null); }}>Escolher outro ficheiro</button>
              </div>
            </>
          )}
        </div>
      )}
      {step === 4 && created && suportado && (
        <div className="stack">
          <p className="ok">✓ Conta «{created.nome}» criada.</p>
          <p>Passo seguinte: carregar o extrato (pré-visualização antes de gravar) e depois categorizar.</p>
          <div className="row"><button className="primary" onClick={() => nav(`/importar?conta=${created.id}`)}>Importar extrato</button><button className="link" onClick={recomecar}>Adicionar outra conta</button></div>
        </div>
      )}
      {step === 4 && created && !suportado && (
        <div className="stack">
          <p className="ok">✓ Conta «{created.nome}» criada ({created.parser_id === "generico" ? "com o modelo detetado" : "banco por suportar"}).</p>
          {created.parser_id === "generico"
            ? <div className="row"><button className="primary" onClick={() => nav(`/importar?conta=${created.id}`)}>Importar extrato</button></div>
            : <>
                <p>Carregue um extrato para ver só o <em>formato</em> (letras viram «x» e dígitos «9»; nada é gravado) e envie esse texto a quem mantém a aplicação.</p>
                <label className="check"><input type="checkbox" checked={rotulos} onChange={(e) => setRotulos(e.target.checked)} /> Mostrar nomes de colunas e rótulos sem máscara (confirme primeiro que o cabeçalho não tem dados pessoais)</label>
                <div className="row"><input type="file" accept=".xls,.xlsx,.csv,.txt" aria-label="Extrato" onChange={(e) => { const f = e.target.files?.[0]; if (f) void analisar(f); }} />{busy && <span className="muted">A analisar…</span>}</div>
                {estrutura && (<><pre className="mask-out" tabIndex={0} aria-label="Estrutura mascarada">{estrutura}</pre>
                  <div className="row"><button className="primary" onClick={() => void copiar()}>{copied ? "Copiado ✓" : "Copiar"}</button><span className="muted small">Reveja antes de partilhar.</span></div></>)}
              </>}
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
