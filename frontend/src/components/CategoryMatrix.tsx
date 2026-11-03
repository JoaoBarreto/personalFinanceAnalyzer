import { eur, mesCurto } from "../lib/format";

export type Matrix = {
  meses: string[];
  linhas: { categoria_id: number | null; nome: string; valores: Record<string, string>; total: string }[];
  totais: Record<string, string>;
  total: string;
};

/** Despesas por categoria × mês. Tabela simples, sem codificação por cor. */
export default function CategoryMatrix({ m }: { m: Matrix }) {
  if (m.linhas.length === 0) return <p className="muted">Sem despesas neste período.</p>;
  const cell = (v: string) => (v === "0.00" ? <span className="muted">—</span> : eur(v));
  return (
    <div className="matrix-wrap">
      <table className="data matrix">
        <thead>
          <tr>
            <th>Categoria</th>
            {m.meses.map((x) => <th key={x} className="num">{mesCurto(x)}</th>)}
            <th className="num">Total</th>
          </tr>
        </thead>
        <tbody>
          {m.linhas.map((l) => (
            <tr key={l.categoria_id ?? "none"}>
              <th scope="row">{l.nome}</th>
              {m.meses.map((x) => <td key={x} className="num">{cell(l.valores[x])}</td>)}
              <td className="num"><strong>{eur(l.total)}</strong></td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row">Total</th>
            {m.meses.map((x) => <td key={x} className="num">{cell(m.totais[x])}</td>)}
            <td className="num"><strong>{eur(m.total)}</strong></td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
