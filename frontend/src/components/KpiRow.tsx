import { eur, mesPt, pct } from "../lib/format";
import InfoTip from "./InfoTip";

export type Kpis = {
  referencia?: { ate: string; ultimo_mes_completo: string; mes_em_curso: boolean };
  reserva_meses: string | null;
  taxa_ano: { ano: number; meses: number; pct: string | null } | null;
  taxa_6m: { meses: number; pct: string | null } | null;
  investido: { ano: string; total: string; serie: { periodo: string; valor: string }[] } | null;
};

const num = (s: string) => Number(s);

/** Reserva, taxa de poupança (acumulada e média) e dinheiro investido. Meses incompletos ficam fora (ver backend). */
export default function KpiRow({ k }: { k: Kpis }) {
  if (!k.investido) return null;
  const serie = k.investido.serie;
  const peak = Math.max(1, ...serie.map((s) => Math.max(0, num(s.valor))));
  const ano = k.taxa_ano?.ano;
  return (
    <section className="kpis3" aria-label="Indicadores de poupança">
      <div className="tile">
        <span className="kpi-label">Reserva<InfoTip title="Reserva"><p>Quantos meses aguentava com o saldo atual, ao ritmo de despesa dos últimos meses: saldo da conta ÷ despesa mensal média dos últimos 6 meses completos.</p><p>Não conta o dinheiro enviado para poupança/investimento nem transferências. Precisa de pelo menos 3 meses completos; o mês em curso fica de fora.</p></InfoTip></span>
        <span className="tile-value">{k.reserva_meses === null ? "n/d" : `${k.reserva_meses.replace(".", ",")} meses`}</span>
        <span className="kpi-sub small">saldo ÷ despesa média mensal{k.taxa_6m && k.taxa_6m.meses > 0 ? ` (${k.taxa_6m.meses} ${k.taxa_6m.meses === 1 ? "mês" : "meses"})` : ""}</span>
      </div>
      <div className="tile">
        <span className="kpi-label">Taxa de poupança{ano ? ` ${ano}` : ""}<InfoTip title="Taxa de poupança acumulada"><p>(Receitas − despesas) ÷ receitas, somando os meses completos do ano. O dinheiro enviado para poupança/investimento conta como poupado; as transferências não contam nem como receita nem como despesa.</p><p>O mês em curso fica de fora: o salário entra no fim do mês anterior e o investimento sai no início, por isso um mês incompleto engana. A média de 6 meses suaviza as oscilações entre meses.</p></InfoTip></span>
        <span className="tile-value">{k.taxa_ano?.pct == null ? "n/d" : pct(k.taxa_ano.pct)}</span>
        <span className="kpi-sub small">acumulada{k.taxa_ano && k.taxa_ano.meses > 0 ? ` (${k.taxa_ano.meses} ${k.taxa_ano.meses === 1 ? "mês" : "meses"})` : ""} · média 6 meses: {k.taxa_6m?.pct == null ? "n/d" : pct(k.taxa_6m.pct)}</span>
      </div>
      <div className="tile">
        <span className="kpi-label">Investido / poupado<InfoTip title="Investido / poupado"><p>Dinheiro que saiu da conta para poupança ou investimento (categorias do tipo transferência, ex.: «Poupança/Investimento»), líquido de entradas. Os valores são acumulados até à data do período escolhido.</p><p>As barras mostram os últimos 12 meses.</p></InfoTip></span>
        <span className="tile-value">{eur(k.investido.ano)}</span>
        <span className="kpi-sub small">em {ano ?? "—"} · {eur(k.investido.total)} desde o início</span>
        <div className="minibars" role="img" aria-label="Investido por mês, últimos 12 meses">
          {serie.map((s) => (
            <span key={s.periodo} className="minibar" title={`${mesPt(s.periodo)}: ${eur(s.valor)}`} style={{ height: `${Math.max(num(s.valor) > 0 ? 6 : 2, (Math.max(0, num(s.valor)) / peak) * 100)}%` }} />
          ))}
        </div>
      </div>
    </section>
  );
}
