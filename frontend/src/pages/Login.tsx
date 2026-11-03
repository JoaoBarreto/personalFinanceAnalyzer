import { useState, type FormEvent } from "react";
import { errorMessage } from "../api";
import { useAuth } from "../auth";

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
    <main className="login">
      <form onSubmit={submit} className="card">
        <h1>Finanças pessoais</h1>
        <label>Utilizador<input value={username} onChange={(e) => setU(e.target.value)} autoComplete="username" autoFocus required /></label>
        <label>Password<input type="password" value={password} onChange={(e) => setP(e.target.value)} autoComplete="current-password" required /></label>
        {err && <p className="error" role="alert">{err}</p>}
        <button className="primary" disabled={busy}>{busy ? "A entrar…" : "Entrar"}</button>
      </form>
    </main>
  );
}
