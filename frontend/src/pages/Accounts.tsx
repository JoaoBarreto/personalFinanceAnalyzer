import { useState } from "react";
import { api, errorMessage, type Account, type User } from "../api";
import { useAsync } from "../hooks";

export default function Accounts() {
  const accounts = useAsync(() => api.get<Account[]>("/api/accounts"), []);
  const users = useAsync(() => api.get<User[]>("/api/users"), []);
  const [nome, setNome] = useState("");
  const [banco, setBanco] = useState("Bankinter");
  const [titular, setTitular] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const wrap = async (fn: () => Promise<void>) => {
    try {
      setErr(null);
      await fn();
    } catch (e) {
      setErr(errorMessage(e));
    }
  };
  const titularSelect = (value: string, onChange: (v: string) => void, label: string) => (
    <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}>
      <option value="">Conjunta</option>
      {users.data?.map((u) => (
        <option key={u.id} value={u.id}>
          {u.nome}
        </option>
      ))}
    </select>
  );
  return (
    <>
      <div className="toolbar"><h1>Contas</h1></div>
      {err && <p className="error" role="alert">{err}</p>}
      <form
        className="card row"
        onSubmit={(e) => {
          e.preventDefault();
          void wrap(async () => {
            await api.post("/api/accounts", { nome, banco, parser_id: "bankinter", titular_id: titular ? Number(titular) : null });
            setNome("");
            accounts.reload();
          });
        }}
      >
        <input placeholder="Nome da conta (ex.: Bankinter Esposa)" value={nome} onChange={(e) => setNome(e.target.value)} required />
        <input placeholder="Banco" value={banco} onChange={(e) => setBanco(e.target.value)} required />
        {titularSelect(titular, setTitular, "Titular da nova conta")}
        <button className="primary">Criar conta</button>
      </form>
      <div className="card flush">
        <table className="data">
          <thead><tr><th>Nome</th><th>Banco</th><th>Titular</th><th>Estado</th></tr></thead>
          <tbody>
            {accounts.data?.map((a) => (
              <tr key={a.id} className={a.arquivada ? "muted" : ""}>
                <td>{a.nome}</td>
                <td>{a.banco}</td>
                <td>
                  {titularSelect(a.titular_id?.toString() ?? "", (v) => wrap(async () => { await api.patch(`/api/accounts/${a.id}`, { titular_id: v ? Number(v) : null }); accounts.reload(); }), `Titular de ${a.nome}`)}
                </td>
                <td>
                  <button className="link" onClick={() => wrap(async () => { await api.patch(`/api/accounts/${a.id}`, { arquivada: !a.arquivada }); accounts.reload(); })}>
                    {a.arquivada ? "Arquivada · reativar" : "Ativa · arquivar"}
                  </button>
                </td>
              </tr>
            ))}
            {accounts.data?.length === 0 && <tr><td colSpan={4} className="muted">Sem contas.</td></tr>}
          </tbody>
        </table>
      </div>
      <p className="muted small">«Conjunta» = sem titular. Os utilizadores criam-se no servidor com <code>python -m app.cli create-user</code>.</p>
    </>
  );
}
