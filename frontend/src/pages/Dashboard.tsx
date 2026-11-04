import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, type Coverage } from "../api";
import CategoryMatrix, { type Matrix } from "../components/CategoryMatrix";
import { CategoryBars, PeriodChart, type CatItem, type PeriodItem } from "../components/charts";
import { CoverageBanner } from "../components/Coverage";
import TitularSelect from "../components/TitularSelect";
import { useAsync } from "../hooks";
import InfoTip from "../components/InfoTip";
import { dataPt, eur, mesPt, pct } from "../lib/format";

type Summary = {
  periodo: { data_de: string; data_ate: string };
  despesas: string; receitas: string; poupanca: string; investido: string; taxa_poupanca_pct: string | null;
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
  // O estado vive no endereço: «Voltar» do browser e recarregar mantêm o período, o modo e os filtros.
  const [sp, setSp] = useSearchParams();
  const modo: "mes" | "ano" = sp.get("modo") === "ano" ? "ano" : "mes";
  const mes = sp.get("mes") ?? "";
  const ano = sp.get("ano") ?? "";
  const titular = sp.get("titular") ?? "";
  const setParam = (k: string, v: string) =>
    setSp((prev) => { const n = new URLSearchParams(prev); if (v) n.set(k, v); else n.delete(k); return n; }, { replace: true });
  const setModo = (m: "mes" | "ano") => setParam("modo", m === "ano" ? "ano" : "");
  const setMes = (v: string) => setParam("mes", v);
  const setAno = (v: string) => setParam("ano", v);
  const setTitular = (v: string) => setParam("titular", v);
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
  const common = { ...params, titular };
  const deps = [ready, modo, ym, titular];

  const summary = useAsync(() => (ready ? api.get<Summary>("/api/analytics/summary", common) : Promise.resolve(null)), deps);
  const cats = useAsync(() => (ready ? api.get<{ itens: CatItem[] }>("/api/analytics/by-category", common) : Promise.resolve(null)), deps);
  // Gráfico do período: em «Mês», os 12 meses até ao mês escolhido; em «Ano», janeiro–dezembro desse ano.
  const periodos = useAsync(
    () => (ready ? api.get<{ periodos: PeriodItem[] }>("/api/analytics/monthly", modo === "ano" ? common : { titular, data_ate: params.data_ate }) : Promise.resolve(null)),
    deps,
  );
  const anos = useAsync(() => (ready ? api.get<{ periodos: PeriodItem[] }>("/api/analytics/monthly", { granularidade: "ano", titular }) : Promise.resolve(null)), [ready, titular]);
  const anoMatriz = ym.slice(0, 4);
  const matrix = useAsync(
    () => (ready && anoMatriz ? api.get<Matrix>("/api/analytics/category-matrix", { data_de: `${anoMatriz}-01-01`, data_ate: `${anoMatriz}-12-31`, titular }) : Promise.resolve(null)),
    [ready, anoMatriz, titular],
  );

  const s = summary.data;
  const step = (d: number) => {
    if (modo === "ano") setAno(String(Number(anoEf) + d));
    else { const [y, m] = mesEf.split("-").map(Number); const t = new Date(y, m - 1 + d, 1); setMes(`${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}`); }
  };
  // Clicar numa barra abre os movimentos desse mesmo período e filtros (os totais têm de bater com a barra).
  const drill = (id: number | null) => {
    const q = new URLSearchParams({ so_despesas: "1" });
    const per = params as { data_de?: string; data_ate?: string };
    if (per.data_de && per.data_ate) { q.set("data_de", per.data_de); q.set("data_ate", per.data_ate); }
    if (titular) q.set("titular", titular);
    if (id === null) q.set("sem_categoria", "true"); else q.set("categoria_id", String(id));
    nav(`/movimentos?${q}`, { state: { from: "dashboard" } });
  };
  const anterior = modo === "ano" ? "ano anterior" : "mês anterior";
  // O saldo é o do último movimento até ao fim do período: se o período ainda não acabou (ou os dados
  // terminam antes), mostrar a data real dos dados em vez de 31/12 ou do fim do mês.
  const dataSaldo = s && ultimo && ultimo < s.periodo.data_ate && ultimo >= s.periodo.data_de ? ultimo : s?.periodo.data_ate ?? "";
  const periodo = modo === "ano" ? `todo o ano de ${ym} (1 jan – 31 dez)` : `o mês de ${ym ? mesPt(ym) : "…"}`;
  const noPeriodo = modo === "ano" ? `em ${periodo}` : `n${periodo}`; // «em todo o ano…» / «no mês de…»
  const doPeriodo = modo === "ano" ? `de ${periodo}` : `d${periodo}`; // «de todo o ano…» / «do mês de…»
  return (
    <>
      <div className="toolbar">
        <h1>Dashboard</h1>
        <div className="seg" role="group" aria-label="Período">
          <button className={modo === "mes" ? "on" : ""} aria-pressed={modo === "mes"} onClick={() => setModo("mes")}>Mês</button>
          <button className={modo === "ano" ? "on" : ""} aria-pressed={modo === "ano"} onClick={() => setModo("ano")}>Ano</button>
        </div>
        <div className="stepper">
          <button onClick={() => step(-1)} aria-label={modo === "ano" ? "Ano anterior" : "Mês anterior"} disabled={!ym}>‹</button>
          {modo === "mes" ? (
            <input type="month" aria-label="Mês" value={mesEf} onChange={(e) => setMes(e.target.value)} />
          ) : (
            <input type="number" aria-label="Ano" min={2000} max={2100} value={anoEf} onChange={(e) => setAno(e.target.value)} style={{ width: "6rem" }} />
          )}
          <button onClick={() => step(1)} aria-label={modo === "ano" ? "Ano seguinte" : "Mês seguinte"} disabled={!ym}>›</button>
        </div>
        <TitularSelect value={titular} onChange={setTitular} />
        {s && s.n_por_categorizar > 0 && <Link className="badge warn" to="/rever">{s.n_por_categorizar} por categorizar</Link>}
      </div>
      <CoverageBanner />
      {summary.error && <p className="error">{summary.error}</p>}
      {s && (
        <>
          <section className="kpis">
            <div className="hero">
              <span className="kpi-label">Saldo da conta<InfoTip title="Saldo da conta"><p>Dinheiro que tem na conta no <strong style={{ display: "inline" }}>fim do período</strong>, lido da coluna «Saldo» do último movimento até essa data.</p><p>Não depende das categorias.</p></InfoTip></span>
              <span className="hero-value">{eur(s.saldo.fim)}</span>
              <span className="kpi-sub">em {dataPt(dataSaldo)}</span>
            </div>
            <div className="tile">
              <span className="kpi-label">Poupança do período<InfoTip title="Poupança do período"><p>Receitas menos despesas {doPeriodo}: o que ficou na conta.</p><p>«Poupado/investido fora da conta» é o dinheiro que enviou para fora (Interactive Brokers, depósitos a prazo...) e que continua a ser seu. Aparece nas despesas como «Poupança/Investimento», mas conta como poupado.</p><p>Taxa de poupança = (poupança + investido fora da conta) ÷ receitas, sem contar as transferências entre as suas contas.</p></InfoTip></span><span className="tile-value">{eur(s.poupanca)}</span>
              {Number(s.investido) > 0 && <span className="kpi-sub small">+ {eur(s.investido)} poupados/investidos fora da conta</span>}
              <span className="kpi-sub small">Taxa de poupança {pct(s.taxa_poupanca_pct)}</span>
            </div>
            <div className="tile">
              <span className="kpi-label">Receitas<InfoTip title="Receitas"><p>Soma dos movimentos de entrada (valor positivo) {doPeriodo}.</p><p>A variação compara com o {anterior}: (atual − anterior) ÷ anterior.</p></InfoTip></span><span className="tile-value">{eur(s.receitas)}</span>
              <Delta v={s.anterior.variacao_receitas_pct} upIsGood label={anterior} />
            </div>
            <div className="tile">
              <span className="kpi-label">Despesas<InfoTip title="Despesas"><p>Soma dos movimentos de saída (valor negativo) {doPeriodo}. Os reembolsos não são descontados.</p><p>A variação compara com o {anterior}.{modo === "mes" ? " A «média 6 meses» é a média mensal dos 6 meses completos anteriores ao mês escolhido (só desde o 1.º movimento)." : ""}</p></InfoTip></span><span className="tile-value">{eur(s.despesas)}</span>
              <Delta v={s.anterior.variacao_despesas_pct} upIsGood={false} label={anterior} />
              {modo === "mes" && <Delta v={s.media_6m.variacao_despesas_pct} upIsGood={false} label="média 6 meses" />}
            </div>
          </section>
          {s.saldo.inicio !== null && (
            <section className="card bridge" aria-label="Do saldo inicial ao final">
              <h2>Do saldo inicial ao final<InfoTip title="Do saldo inicial ao final"><p>Saldo inicial + receitas − despesas = saldo final.</p><p>Todos os movimentos contam, incluindo transferências e «Poupança/Investimento» (dinheiro enviado para a corretora, depósitos a prazo...). Se as contas não fecharem, faltam movimentos: veja o aviso de cobertura.</p></InfoTip></h2>
              <dl>
                <dt>{primeiro && primeiro > s.periodo.data_de ? `Saldo antes do 1.º movimento (${dataPt(primeiro)})` : `Saldo inicial (${dataPt(s.periodo.data_de)})`}</dt><dd>{eur(s.saldo.inicio)}</dd>
                <dt>+ Receitas</dt><dd>{eur(s.receitas)}</dd>
                <dt>− Despesas</dt><dd>{eur(s.despesas)}</dd>
                <dt className="strong">= Saldo final ({dataPt(dataSaldo)})</dt><dd className="strong">{eur(s.saldo.fim)}</dd>
              </dl>
              {s.saldo.reconcilia === true && <p className="ok small">✓ As contas fecham ao cêntimo.</p>}
              {s.saldo.reconcilia === false && <p className="warn-text small">✗ Não fecha (diferença {eur(s.saldo.diferenca)}): provavelmente faltam movimentos. Veja o aviso de cobertura acima ou importe o período em falta.</p>}
            </section>
          )}
        </>
      )}
      <div className="grid2">
        <section className="card">
          <h2>
            Despesas por categoria
            <InfoTip title="Como se calcula">
              <p>Dinheiro que <strong style={{ display: "inline" }}>saiu</strong> da conta {noPeriodo}, somado por categoria. Contam os movimentos de saída (valor negativo); entradas e reembolsos não são descontados.</p>
              <p>Respeita o filtro de titular.</p>
              <p>A percentagem é o valor da categoria ÷ total das despesas do período (somam 100 %).</p>
              <p>«Por categorizar» são movimentos ainda sem categoria; «Outros (N)» junta as N categorias mais pequenas. Clique numa barra para ver os movimentos.</p>
            </InfoTip>
          </h2>
          {cats.data && cats.data.itens.length === 0 && <p className="muted">Sem despesas neste período.</p>}
          {cats.data && cats.data.itens.length > 0 && (
            <CategoryBars items={cats.data.itens} onPick={drill} />
          )}
        </section>
        <section className="card">
          <h2>{modo === "ano" ? `Evolução mensal em ${ym}` : "Evolução mensal (12 meses)"}<InfoTip title="Evolução mensal"><p>Receitas e despesas de cada mês (barras) e poupança = receitas − despesas (linha).</p><p>{modo === "ano" ? "Mostra janeiro a dezembro do ano escolhido." : "Mostra os 12 meses até ao mês escolhido."} O último mês com dados não mostra poupança (ainda está incompleto). «Ver tabela» dá os números e o saldo no fim de cada mês.</p></InfoTip></h2>
          {periodos.data && <PeriodChart parcialEm={ultimo?.slice(0, 7)} periodos={periodos.data.periodos} titulo="Receitas, despesas e poupança por mês" />}
        </section>
      </div>
      <section className="card">
        <h2>Despesas por categoria e mês, {anoMatriz}<InfoTip title="Categoria × mês"><p>Despesas de cada categoria-pai em cada mês de {anoMatriz}, com o total por categoria e por mês. Mesmo critério das barras: saídas.</p></InfoTip></h2>
        {matrix.data && <CategoryMatrix m={matrix.data} />}
      </section>
      <section className="card">
        <h2>Por ano<InfoTip title="Por ano"><p>Receitas, despesas e poupança de cada ano com movimentos (1 jan – 31 dez).</p></InfoTip></h2>
        {anos.data && <PeriodChart periodos={anos.data.periodos} titulo="Receitas, despesas e poupança por ano" />}
      </section>
    </>
  );
}
