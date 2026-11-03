import { useState } from "react";
import { eur, fromCents, mesPt, toCents } from "../lib/format";

const MES_CURTO = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
function tickLabel(ym: string, first: boolean): string {
  const [y, m] = ym.split("-");
  return first || m === "01" ? `${MES_CURTO[Number(m) - 1]} ${y}` : MES_CURTO[Number(m) - 1];
}

export type CatItem = { categoria_id: number | null; nome: string; total: string; n: number; percentagem: string | null };
export type MonthItem = { mes: string; despesas: string; receitas: string; saldo_liquido: string };

/** Barras horizontais por categoria: top N + "Outros"; valor na ponta; barra <= 16px, ponta de dados com 4px. */
export function CategoryBars({ items, onPick, max = 8 }: { items: CatItem[]; onPick?: (id: number | null) => void; max?: number }) {
  const [tip, setTip] = useState<string | null>(null);
  const head = items.slice(0, max);
  const rest = items.slice(max);
  const rows: (CatItem & { folded?: boolean })[] = [...head];
  if (rest.length) {
    const sum = rest.reduce((a, r) => a + toCents(r.total), 0);
    rows.push({ categoria_id: -1, nome: `Outros (${rest.length})`, total: fromCents(sum), n: rest.reduce((a, r) => a + r.n, 0), percentagem: null, folded: true });
  }
  const peak = Math.max(1, ...rows.map((r) => toCents(r.total)));
  return (
    <div className="hbar" role="list" aria-label="Despesas por categoria">
      {rows.map((r) => {
        const w = (toCents(r.total) / peak) * 100;
        const pick = !r.folded && onPick;
        return (
          <div
            role="listitem"
            className={`hbar-row${pick ? " clickable" : ""}`}
            key={r.categoria_id ?? "none"}
            onMouseEnter={() => setTip(`${r.nome}: ${eur(r.total)} · ${r.n} mov.${r.percentagem ? ` · ${r.percentagem.replace(".", ",")} %` : ""}`)}
            onMouseLeave={() => setTip(null)}
            onClick={pick ? () => onPick(r.categoria_id) : undefined}
          >
            <div className="hbar-label" title={r.nome}>
              {r.nome}
            </div>
            <div className="hbar-track">
              <div className={`hbar-fill${r.categoria_id === null ? " muted" : ""}`} style={{ width: `${Math.max(w * 0.8, 0.5)}%` }} />
              <span className="hbar-value">{eur(r.total)}</span>
            </div>
          </div>
        );
      })}
      <div className="tip-line" aria-live="polite">
        {tip ?? " "}
      </div>
    </div>
  );
}

function niceMax(v: number): number {
  if (v <= 0) return 100;
  const p = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 2, 2.5, 5, 10]) if (v <= m * p) return m * p;
  return 10 * p;
}
const axis = (c: number) => Math.round(c / 100).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");

/** Receitas vs despesas (barras agrupadas, 1 eixo) + linha do saldo líquido. Legenda sempre visível. */
export function MonthlyChart({ meses }: { meses: MonthItem[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const W = 720, H = 300, L = 56, R = 76, T = 16, B = 34;
  const iw = W - L - R, ih = H - T - B;
  const vals = meses.flatMap((m) => [toCents(m.despesas), toCents(m.receitas), toCents(m.saldo_liquido)]);
  const top = niceMax(Math.max(0, ...vals));
  const bottom = Math.min(0, ...vals) < 0 ? -niceMax(-Math.min(...vals)) : 0;
  const y = (c: number) => T + ih - ((c - bottom) / (top - bottom)) * ih;
  const band = iw / Math.max(meses.length, 1);
  const bw = Math.min(24, band / 3);
  const gap = 2;
  const ticks = Array.from({ length: 5 }, (_, i) => bottom + ((top - bottom) * i) / 4);
  const x0 = (i: number) => L + band * i + band / 2;
  const bar = (cx: number, c: number) => {
    const y1 = y(Math.max(c, 0)), y0 = y(0), h = Math.max(y0 - y1, 0);
    const r = Math.min(4, h);
    return h === 0 ? "" : `M${cx},${y0} V${y1 + r} Q${cx},${y1} ${cx + r},${y1} H${cx + bw - r} Q${cx + bw},${y1} ${cx + bw},${y1 + r} V${y0} Z`;
  };
  const has = (m: MonthItem) => toCents(m.receitas) !== 0 || toCents(m.despesas) !== 0;
  let line = "";
  meses.forEach((m, i) => {
    if (!has(m)) return;
    line += `${i > 0 && has(meses[i - 1]) ? "L" : "M"}${x0(i)},${y(toCents(m.saldo_liquido))} `;
  });
  const lastIdx = meses.map(has).lastIndexOf(true);
  const last = lastIdx >= 0 ? meses[lastIdx] : undefined;
  return (
    <div className="chart-wrap">
      <div className="chart-head">
        <ul className="legend" aria-label="Legenda">
          <li><span className="sw s1" /> Receitas</li>
          <li><span className="sw s2" /> Despesas</li>
          <li><span className="sw s3 line" /> Saldo líquido</li>
        </ul>
        <button className="link" onClick={() => setTable(!table)}>{table ? "Ver gráfico" : "Ver tabela"}</button>
      </div>
      {table ? (
        <table className="data">
          <thead><tr><th>Mês</th><th className="num">Receitas</th><th className="num">Despesas</th><th className="num">Saldo líquido</th></tr></thead>
          <tbody>
            {meses.map((m) => (
              <tr key={m.mes}><td>{mesPt(m.mes)}</td><td className="num">{eur(m.receitas)}</td><td className="num">{eur(m.despesas)}</td><td className="num">{eur(m.saldo_liquido)}</td></tr>
            ))}
          </tbody>
        </table>
      ) : (
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Receitas, despesas e saldo líquido por mês" className="chart">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} className={t === 0 ? "baseline" : "grid"} />
              <text x={L - 8} y={y(t) + 4} textAnchor="end" className="axis-text">{axis(t)}</text>
            </g>
          ))}
          {meses.map((m, i) => (
            <g key={m.mes}>
              <path d={bar(x0(i) - bw - gap / 2, toCents(m.receitas))} className="s1" />
              <path d={bar(x0(i) + gap / 2, toCents(m.despesas))} className="s2" />
              <text x={x0(i)} y={H - 12} textAnchor="middle" className="axis-text">{tickLabel(m.mes, i === 0)}</text>
            </g>
          ))}
          <path d={line} className="net-line" fill="none" />
          {meses.map((m, i) => has(m) && (
            <circle key={m.mes} cx={x0(i)} cy={y(toCents(m.saldo_liquido))} r={4} className="net-dot" />
          ))}
          {last && <text x={x0(lastIdx) + 10} y={y(toCents(last.saldo_liquido)) + 4} className="end-label">{eur(last.saldo_liquido)}</text>}
          {meses.map((m, i) => (
            <rect key={m.mes} x={L + band * i} y={T} width={band} height={ih} fill="transparent"
              onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} />
          ))}
        </svg>
      )}
      {!table && hover !== null && (
        <div className="tooltip" style={{ left: `${(x0(hover) / W) * 100}%` }}>
          <strong>{mesPt(meses[hover].mes)}</strong>
          <div>Receitas {eur(meses[hover].receitas)}</div>
          <div>Despesas {eur(meses[hover].despesas)}</div>
          <div>Saldo {eur(meses[hover].saldo_liquido)}</div>
        </div>
      )}
    </div>
  );
}
