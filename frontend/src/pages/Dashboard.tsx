import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { CategoryBars, MonthlyChart, type CatItem, type MonthItem } from "../components/charts";
import TitularSelect from "../components/TitularSelect";
import { useAsync } from "../hooks";
import { eur, pct } from "../lib/format";

type Summary = {
  periodo: { data_de: string; data_ate: string };
  despesas: string; receitas: string; saldo_liquido: string; taxa_poupanca_pct: string | null;
  anterior: { variacao_despesas_pct: string | null; variacao_receitas_pct: string | null };
  media_6m: { despesas: string; variacao_despesas_pct: string | null };
  n_por_categorizar: number;
};

function lastDay(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  return `${ym}-${String(new Date(y, m, 0).getDate()).padStart(2, "0")}`;
}

/** Delta com sinal e seta; para despesas, subir é mau (cor segue a direção × se subir é bom). */
function Delta({ v, upIsGood, label }: { v: string | null; upIsGood: boolean; label: string }) {
  if (v === null) return <span className="delta muted">sem {label}</span>;
  const up = Number(v) > 0, zero = Number(v) === 0;
  const good = zero ? null : up === upIsGood;
  return (
    <span className={`delta ${good === null ? "muted" : good ? "good" : "bad"}`}>
      {zero ? "=" : up ? "▲" : "▼"} {pct(v.replace("-", ""))} vs {label}
    </span>
  );
}

export default function Dashboard() {
  const [mes, setMes] = useState("");
  const [transf, setTransf] = useState(false);
  const [titular, setTitular] = useState("");
  const nav = useNavigate();
  const params = mes ? { data_de: `${mes}-01`, data_ate: lastDay(mes) } : {};
  const common = { ...params, incluir_transferencias: transf, titular };
  const summary = useAsync(() => api.get<Summary>("/api/analytics/summary", common), [mes, transf, titular]);
  const cats = useAsync(() => api.get<{ itens: CatItem[] }>("/api/analytics/by-category", common), [mes, transf, titular]);
  const monthly = useAsync(
    () => api.get<{ meses: MonthItem[] }>("/api/analytics/monthly", { incluir_transferencias: transf, data_ate: params.data_ate, titular }),
    [mes, transf, titular],
  );
  const s = summary.data;
  return (
    <>
      <div className="toolbar">
        <h1>Dashboard</h1>
        <label>Mês <input type="month" value={mes || (s?.periodo.data_de.slice(0, 7) ?? "")} onChange={(e) => setMes(e.target.value)} /></label>
        <TitularSelect value={titular} onChange={setTitular} />
        <label className="check"><input type="checkbox" checked={transf} onChange={(e) => setTransf(e.target.checked)} /> Incluir transferências</label>
        {s && s.n_por_categorizar > 0 && <Link className="badge warn" to="/rever">{s.n_por_categorizar} por categorizar</Link>}
      </div>
      {summary.error && <p className="error">{summary.error}</p>}
      {s && (
        <section className="kpis">
          <div className="hero">
            <span className="kpi-label">Saldo líquido</span>
            <span className="hero-value">{eur(s.saldo_liquido)}</span>
            <span className="kpi-sub">Taxa de poupança {pct(s.taxa_poupanca_pct)}</span>
          </div>
          <div className="tile">
            <span className="kpi-label">Receitas</span><span className="tile-value">{eur(s.receitas)}</span>
            <Delta v={s.anterior.variacao_receitas_pct} upIsGood label="mês anterior" />
          </div>
          <div className="tile">
            <span className="kpi-label">Despesas</span><span className="tile-value">{eur(s.despesas)}</span>
            <Delta v={s.anterior.variacao_despesas_pct} upIsGood={false} label="mês anterior" />
            <Delta v={s.media_6m.variacao_despesas_pct} upIsGood={false} label="média 6 meses" />
          </div>
        </section>
      )}
      <div className="grid2">
        <section className="card">
          <h2>Despesas por categoria</h2>
          {cats.data && cats.data.itens.length === 0 && <p className="muted">Sem despesas neste período.</p>}
          {cats.data && cats.data.itens.length > 0 && (
            <CategoryBars items={cats.data.itens} onPick={(id) => nav(id === null ? "/rever" : `/movimentos?categoria_id=${id}`)} />
          )}
        </section>
        <section className="card">
          <h2>Evolução mensal</h2>
          {monthly.data && <MonthlyChart meses={monthly.data.meses} />}
        </section>
      </div>
    </>
  );
}
