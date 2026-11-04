import { useState } from "react";
import { api, errorMessage, type Account } from "../api";
import { useAsync } from "../hooks";

export default function Accounts() {
  const accounts = useAsync(() => api.get<Account[]>("/api/accounts"), []);
  const [nome, setNome] = useState("");
  const [banco, setBanco] = useState("Bankinter");
  const [err, setErr] = useState<string | null>(null);
  const wrap = async (fn: () => Promise<void>) => {
    try {
      setErr(null);
      await fn();
    } catch (e) {
      setErr(errorMessage(e));
    }
  };
  return (
    <>
      <div className="toolbar"><h1>Contas</h1></div>
      {err && <p className="error" role="alert">{err}</p>}
      <form
        className="card row"
        onSubmit={(e) => {
          e.preventDefault();
          void wrap(async () => {
            await api.post("/api/accounts", { nome, banco, parser_id: "bankinter" });
            setNome("");
            accounts.reload();
          });
        }}
      >
        <input placeholder="Nome da conta (ex.: Ordenado)" value={nome} onChange={(e) => setNome(e.target.value)} required />
        <input placeholder="Banco" value={banco} onChange={(e) => setBanco(e.target.value)} required />
        <button className="primary">Criar conta</button>
      </form>
      <div className="card flush">
        <table className="data">
          <thead><tr><th>Nome</th><th>Banco</th><th>Estado</th></tr></thead>
          <tbody>
            {accounts.data?.map((a) => (
              <tr key={a.id} className={a.arquivada ? "muted" : ""}>
                <td>{a.nome}</td>
                <td>{a.banco}</td>
                <td>
                  <button className="link" onClick={() => wrap(async () => { await api.patch(`/api/accounts/${a.id}`, { arquivada: !a.arquivada }); accounts.reload(); })}>
                    {a.arquivada ? "Arquivada · reativar" : "Ativa · arquivar"}
                  </button>
                </td>
              </tr>
            ))}
            {accounts.data?.length === 0 && <tr><td colSpan={3} className="muted">Sem contas.</td></tr>}
          </tbody>
        </table>
      </div>
      <p className="muted small">As contas são só suas: mais ninguém as vê. Os utilizadores criam-se no servidor com <code>python -m app.cli create-user</code>.</p>
    </>
  );
}
