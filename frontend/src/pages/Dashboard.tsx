import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type Coverage } from "../api";
import CategoryMatrix, { type Matrix } from "../components/CategoryMatrix";
import { CategoryBars, PeriodChart, type CatItem, type PeriodItem } from "../components/charts";
import { CoverageBanner } from "../components/Coverage";
import TitularSelect from "../components/TitularSelect";
import { useAsync } from "../hooks";
import { dataPt, eur, pct } from "../lib/format";

type Summary = {
  periodo: { data_de: string; data_ate: string };
  despesas: string; receitas: string; poupanca: string; taxa_poupanca_pct: string | null;
  saldo: { inicio: string | null; fim: string | null; transferencias: string; diferenca: string | null; reconcilia: boolean | null };
  anterior: { variacao_despesas_pct: string | null; variacao_receitas_pct: string | null };
  media_6m: { variacao_despesas_pct: string | null };
  n_por_categorizar: number;
};

const lastDay = (ym: string) => {
  const [y, m] = ym.split("-").map(Number);
  return `${ym}-${String(new Date(y, m, 0).getDate()).padStart(2, "0")}`;
};

/** Delta com sinal e seta; para despesas, subir é mau (cor = direção × se subir é bom). */
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
  const [modo, setModo] = useState<"mes" | "ano">("mes");
  const [mes, setMes] = useState("");
  const [ano, setAno] = useState("");
  const [transf, setTransf] = useState(false);
  const [titular, setTitular] = useState("");
  const nav = useNavigate();

  // O período por omissão é o do último movimento importado (e não o mês corrente, que pode estar vazio).
  const cov = useAsync(() => api.get<Coverage[]>("/api/coverage"), []);
  const ultimo = cov.data?.map((c) => c.ultimo).filter((x): x is string => !!x).sort().at(-1);
  const anoEf = ano || ultimo?.slice(0, 4) || "";
  const mesEf = mes || ultimo?.slice(0, 7) || "";
  const primeiro = cov.data?.map((c) => c.primeiro).filter((x): x is string => !!x).sort()[0];
  const ready = !cov.loading;
  const ym = modo === "ano" ? anoEf : mesEf;
  const params = !ym ? {} : modo === "ano" ? { data_de: `${ym}-01-01`, data_ate: `${ym}-12-31` } : { data_de: `${ym}-01`, data_ate: lastDay(ym) };
  const common = { ...params, incluir_transferencias: transf, titular };
  const deps = [ready, modo, ym, transf, titular];

  const summary = useAsync(() => (ready ? api.get<Summary>("/api/analytics/summary", common) : Promise.resolve(null)), deps);
  const cats = useAsync(() => (ready ? api.get<{ itens: CatItem[] }>("/api/analytics/by-category", common) : Promise.resolve(null)), deps);
  // Gráfico do período: em «Mês», os 12 meses até ao mês escolhido; em «Ano», janeiro–dezembro desse ano.
  const periodos = useAsync(
    () => (ready ? api.get<{ periodos: PeriodItem[] }>("/api/analytics/monthly", modo === "ano" ? common : { incluir_transferencias: transf, titular, data_ate: params.data_ate }) : Promise.resolve(null)),
    deps,
  );
  const anos = useAsync(() => (ready ? api.get<{ periodos: PeriodItem[] }>("/api/analytics/monthly", { granularidade: "ano", incluir_transferencias: transf, titular }) : Promise.resolve(null)), [ready, transf, titular]);
  const anoMatriz = ym.slice(0, 4);
  const matrix = useAsync(
    () => (ready && anoMatriz ? api.get<Matrix>("/api/analytics/category-matrix", { data_de: `${anoMatriz}-01-01`, data_ate: `${anoMatriz}-12-31`, incluir_transferencias: transf, titular }) : Promise.resolve(null)),
    [ready, anoMatriz, transf, titular],
  );

  const s = summary.data;
  const anterior = modo === "ano" ? "ano anterior" : "mês anterior";
  return (
    <>
      <div className="toolbar">
        <h1>Dashboard</h1>
        <div className="seg" role="group" aria-label="Período">
          <button className={modo === "mes" ? "on" : ""} aria-pressed={modo === "mes"} onClick={() => setModo("mes")}>Mês</button>
          <button className={modo === "ano" ? "on" : ""} aria-pressed={modo === "ano"} onClick={() => setModo("ano")}>Ano</button>
        </div>
        {modo === "mes" ? (
          <label>Mês <input type="month" value={mesEf} onChange={(e) => setMes(e.target.value)} /></label>
        ) : (
          <label>Ano <input type="number" min={2000} max={2100} value={anoEf} onChange={(e) => setAno(e.target.value)} style={{ width: "6rem" }} /></label>
        )}
        <TitularSelect value={titular} onChange={setTitular} />
        <label className="check"><input type="checkbox" checked={transf} onChange={(e) => setTransf(e.target.checked)} /> Incluir transferências</label>
        {s && s.n_por_categorizar > 0 && <Link className="badge warn" to="/rever">{s.n_por_categorizar} por categorizar</Link>}
      </div>
      <CoverageBanner />
      {summary.error && <p className="error">{summary.error}</p>}
      {s && (
        <>
          <section className="kpis">
            <div className="hero">
              <span className="kpi-label">Saldo da conta</span>
              <span className="hero-value">{eur(s.saldo.fim)}</span>
              <span className="kpi-sub">em {dataPt(s.periodo.data_ate)}</span>
            </div>
            <div className="tile">
              <span className="kpi-label">Poupança do período</span><span className="tile-value">{eur(s.poupanca)}</span>
              <span className="kpi-sub small">Taxa de poupança {pct(s.taxa_poupanca_pct)}</span>
            </div>
            <div className="tile">
              <span className="kpi-label">Receitas</span><span className="tile-value">{eur(s.receitas)}</span>
              <Delta v={s.anterior.variacao_receitas_pct} upIsGood label={anterior} />
            </div>
            <div className="tile">
              <span className="kpi-label">Despesas</span><span className="tile-value">{eur(s.despesas)}</span>
              <Delta v={s.anterior.variacao_despesas_pct} upIsGood={false} label={anterior} />
              {modo === "mes" && <Delta v={s.media_6m.variacao_despesas_pct} upIsGood={false} label="média 6 meses" />}
            </div>
          </section>
          {s.saldo.inicio !== null && (
            <section className="card bridge" aria-label="Do saldo inicial ao final">
              <h2>Do saldo inicial ao final</h2>
              <dl>
                <dt>{primeiro && primeiro > s.periodo.data_de ? `Saldo antes do 1.º movimento (${dataPt(primeiro)})` : `Saldo inicial (${dataPt(s.periodo.data_de)})`}</dt><dd>{eur(s.saldo.inicio)}</dd>
                <dt>+ Receitas</dt><dd>{eur(s.receitas)}</dd>
                <dt>− Despesas</dt><dd>{eur(s.despesas)}</dd>
                {s.saldo.transferencias !== "0.00" && <><dt>± Transferências (fora dos totais)</dt><dd>{eur(s.saldo.transferencias)}</dd></>}
                <dt className="strong">= Saldo final ({dataPt(s.periodo.data_ate)})</dt><dd className="strong">{eur(s.saldo.fim)}</dd>
              </dl>
              {s.saldo.reconcilia === true && <p className="ok small">✓ As contas fecham ao cêntimo.</p>}
              {s.saldo.reconcilia === false && <p className="warn-text small">✗ Não fecha (diferença {eur(s.saldo.diferenca)}): provavelmente faltam movimentos. Veja o aviso de cobertura acima ou importe o período em falta.</p>}
            </section>
          )}
        </>
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
          <h2>{modo === "ano" ? `Evolução mensal em ${ym}` : "Evolução mensal (12 meses)"}</h2>
          {periodos.data && <PeriodChart periodos={periodos.data.periodos} titulo="Receitas, despesas e poupança por mês" />}
        </section>
      </div>
      <section className="card">
        <h2>Despesas por categoria e mês, {anoMatriz}</h2>
        {matrix.data && <CategoryMatrix m={matrix.data} />}
      </section>
      <section className="card">
        <h2>Por ano</h2>
        {anos.data && <PeriodChart periodos={anos.data.periodos} titulo="Receitas, despesas e poupança por ano" />}
      </section>
    </>
  );
}
