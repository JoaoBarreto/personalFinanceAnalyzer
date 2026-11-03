import { useState, type FormEvent } from "react";
import { errorMessage } from "../api";
import { useAuth } from "../auth";
import Logo from "../components/Logo";
import { APP } from "../lib/about";

export default function Login() {
  const { login } = useAuth();
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await login(username, password);
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
          <h2>Iniciar sessão</h2>
          <p className="muted">Aceda às suas finanças.</p>
          <label>Utilizador<input value={username} onChange={(e) => setU(e.target.value)} autoComplete="username" autoFocus required /></label>
          <label>Palavra-passe<input type="password" value={password} onChange={(e) => setP(e.target.value)} autoComplete="current-password" required /></label>
          {err && <p className="error" role="alert">{err}</p>}
          <button className="primary" disabled={busy}>{busy ? "A entrar…" : "Entrar"}</button>
          <p className="login-note muted small">Acesso reservado. Todas as sessões ficam protegidas por palavra-passe.</p>
        </form>
      </main>
    </div>
  );
}
