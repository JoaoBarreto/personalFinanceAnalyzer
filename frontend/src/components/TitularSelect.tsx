import { api, type User } from "../api";
import { useAsync } from "../hooks";

/** Filtro por titular: Todos · cada utilizador · Conjuntas (valor "" | id | "conjunta"). */
export default function TitularSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const users = useAsync(() => api.get<User[]>("/api/users"), []);
  if (!users.data || users.data.length < 2) return null; // com um só utilizador o filtro não faz sentido
  return (
    <label>
      Titular
      <select value={value} onChange={(e) => onChange(e.target.value)} aria-label="Titular">
        <option value="">Todos</option>
        {users.data.map((u) => (
          <option key={u.id} value={u.id}>
            {u.nome}
          </option>
        ))}
        <option value="conjunta">Conjuntas</option>
      </select>
    </label>
  );
}
