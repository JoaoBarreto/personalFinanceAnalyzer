import { useState, type FormEvent } from "react";
import { api, errorMessage } from "../api";
import { useAuth } from "../auth";
import Logo from "../components/Logo";
import { useAsync } from "../hooks";
import { APP } from "../lib/about";

type Config = { registo_aberto: boolean; sem_utilizadores: boolean };

/** Entrar ou criar conta. Sem utilizadores (instalação nova) abre em «Criar conta»: é o primeiro ecrã de quem instala. */
export default function Login() {
  const { login, register } = useAuth();
  const cfg = useAsync(() => api.get<Config>("/api/auth/config"), []);
  const [modo, setModo] = useState<"entrar" | "criar" | null>(null);
  const [username, setU] = useState("");
  const [nome, setNome] = useState("");
  const [password, setP] = useState("");
  const [repetir, setR] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const aberto = cfg.data?.registo_aberto ?? false;
  const primeira = cfg.data?.sem_utilizadores ?? false;
  const atual = modo ?? (primeira ? "criar" : "entrar");

  const trocar = (m: "entrar" | "criar") => { setModo(m); setErr(null); setP(""); setR(""); };
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (atual === "criar") {
      if (password !== repetir) return setErr("As palavras-passe não coincidem.");
      if (password.length < 10) return setErr("A palavra-passe deve ter pelo menos 10 caracteres.");
    }
    setBusy(true);
    try {
      if (atual === "criar") await register(username, nome, password);
      else await login(username, password);
    } catch (x) {
      setErr(errorMessage(x));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="login-shell">
      <aside className="login-brand">
        <div className="login-brand-in">
          <div className="login-logo"><Logo size={44} /><span>{APP.nome}</span></div>
          <h1>Perceba para onde vai o seu dinheiro.</h1>
          <p className="login-tagline">{APP.descricao}.</p>
          <ul>
            <li>Importa o extrato do banco, sem ligações a terceiros</li>
            <li>Categorização por regras que aprende consigo</li>
            <li>Contas que fecham ao cêntimo, por mês e por ano</li>
            <li>Os seus dados ficam apenas neste servidor</li>
          </ul>
        </div>
        <small className="login-copy">© {APP.ano} {APP.autor} · v{APP.versao}</small>
      </aside>
      <main className="login-panel">
        <form onSubmit={submit} className="login-card">
          <h2>{atual === "criar" ? (primeira ? "Criar a primeira conta" : "Criar conta") : "Iniciar sessão"}</h2>
          <p className="muted">
            {atual === "criar"
              ? primeira ? "Ainda não há utilizadores neste servidor: crie a sua conta para começar." : "Cada pessoa só vê os seus próprios dados."
              : "Aceda às suas finanças."}
          </p>
          {atual === "criar" && (
            <label>Nome a mostrar<input value={nome} onChange={(e) => setNome(e.target.value)} autoComplete="name" maxLength={80} required autoFocus /></label>
          )}
          <label>Utilizador
            <input value={username} onChange={(e) => setU(e.target.value)} autoComplete="username" required autoFocus={atual === "entrar"} maxLength={64} />
            {atual === "criar" && <small className="muted">3 a 32 caracteres: letras minúsculas, números, ponto, hífen ou _.</small>}
          </label>
          <label>Palavra-passe
            <input type="password" value={password} onChange={(e) => setP(e.target.value)} autoComplete={atual === "criar" ? "new-password" : "current-password"} required />
            {atual === "criar" && <small className="muted">Pelo menos 10 caracteres.</small>}
          </label>
          {atual === "criar" && (
            <label>Repetir palavra-passe<input type="password" value={repetir} onChange={(e) => setR(e.target.value)} autoComplete="new-password" required /></label>
          )}
          {err && <p className="error" role="alert">{err}</p>}
          <button className="primary" disabled={busy}>{busy ? "A processar…" : atual === "criar" ? "Criar conta" : "Entrar"}</button>
          {aberto && !primeira && (
            <p className="login-note small">
              {atual === "entrar"
                ? <>Ainda não tem conta? <button type="button" className="link" onClick={() => trocar("criar")}>Criar conta</button></>
                : <>Já tem conta? <button type="button" className="link" onClick={() => trocar("entrar")}>Iniciar sessão</button></>}
            </p>
          )}
          {atual === "entrar" && !aberto && <p className="login-note muted small">Acesso reservado. O registo de novos utilizadores está desativado neste servidor.</p>}
        </form>
      </main>
    </div>
  );
}
