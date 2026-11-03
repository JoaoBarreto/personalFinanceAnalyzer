import { Link } from "react-router-dom";
import { api, type Coverage } from "../api";
import { useAsync } from "../hooks";
import { dataPt } from "../lib/format";

/** Aviso quando a cadeia de saldos tem buracos: os agregados podem estar incompletos. */
export function CoverageBanner() {
  const cov = useAsync(() => api.get<Coverage[]>("/api/coverage"), []);
  const bad = cov.data?.filter((c) => !c.ok) ?? [];
  if (bad.length === 0) return null;
  return (
    <div className="card warn-card" role="alert">
      <strong>Podem faltar movimentos.</strong>{" "}
      {bad.map((c) => (
        <span key={c.conta_id}>
          {c.nome}: {c.falhas.length} falha(s) na cadeia de saldos, a primeira entre {dataPt(c.falhas[0].de)} e {dataPt(c.falhas[0].ate)}
          {c.falhas.length > 1 ? ` (e mais ${c.falhas.length - 1})` : ""}.{" "}
        </span>
      ))}
      Muitas falhas seguidas costumam indicar o mesmo extrato importado duas vezes com valores diferentes.{" "}
      <Link to="/importar">Importar o período em falta →</Link>
    </div>
  );
}

/** Resumo do que está importado, por conta (ecrã Importar). */
export function CoverageSummary() {
  const cov = useAsync(() => api.get<Coverage[]>("/api/coverage"), []);
  if (!cov.data || cov.data.every((c) => c.n_movimentos === 0)) return null;
  return (
    <div className="card">
      <h2>Dados importados</h2>
      <ul className="plain">
        {cov.data.filter((c) => c.n_movimentos > 0).map((c) => (
          <li key={c.conta_id}>
            <strong>{c.nome}</strong>: {dataPt(c.primeiro)} a {dataPt(c.ultimo)} · {c.n_movimentos} movimentos ·{" "}
            {c.ok ? <span className="ok">sem falhas</span> : <span className="warn-text">{c.falhas.length} falha(s): {c.falhas.map((f) => `${dataPt(f.de)} → ${dataPt(f.ate)}`).join("; ")}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
