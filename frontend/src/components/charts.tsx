import { useState } from "react";
import { eur, fromCents, mesPt, toCents } from "../lib/format";

const MES_CURTO = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
function tickLabel(p: string, first: boolean): string {
  const [y, m] = p.split("-");
  if (!m) return y; // período anual
  return first || m === "01" ? `${MES_CURTO[Number(m) - 1]} ${y}` : MES_CURTO[Number(m) - 1];
}

export type CatItem = { categoria_id: number | null; nome: string; total: string; n: number; percentagem: string | null };
export type PeriodItem = { periodo: string; despesas: string; receitas: string; poupanca: string; saldo_fim: string | null };

/** Barras horizontais por categoria: top N + «Outros» (que se expande); valor e percentagem ao lado; clicar abre os movimentos. */
export function CategoryBars({ items, onPick, max = 8 }: { items: CatItem[]; onPick?: (id: number | null) => void; max?: number }) {
  const [tip, setTip] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const head = expanded ? items : items.slice(0, max);
  const rest = items.slice(max);
  const rows: (CatItem & { folded?: boolean })[] = [...head];
  if (rest.length && !expanded) {
    const sumRest = rest.reduce((a, r) => a + toCents(r.total), 0);
    rows.push({ categoria_id: -1, nome: `Outros (${rest.length})`, total: fromCents(sumRest), n: rest.reduce((a, r) => a + r.n, 0), percentagem: null, folded: true });
  }
  const peak = Math.max(1, ...rows.map((r) => toCents(r.total)));
  const sum = Math.max(1, rows.reduce((a, r) => a + toCents(r.total), 0));
  // percentagem do total das despesas, com 1 casa decimal, calculada em cêntimos inteiros (as linhas somam 100 %)
  const share = (c: number) => `${(Math.round((c * 1000) / sum) / 10).toFixed(1).replace(".", ",")}\u00a0%`;
  return (
    <div className="hbar" role="list" aria-label="Despesas por categoria">
      {rows.map((r) => {
        const w = (toCents(r.total) / peak) * 100;
        const action = r.folded ? () => setExpanded(true) : onPick ? () => onPick(r.categoria_id) : undefined;
        const hint = r.folded ? "Mostrar as categorias agrupadas" : "Ver os movimentos desta categoria";
        return (
          <div
            role="listitem"
            className={`hbar-row${action ? " clickable" : ""}`}
            key={r.categoria_id ?? "none"}
            tabIndex={action ? 0 : undefined}
            title={action ? hint : undefined}
            onMouseEnter={() => setTip(`${r.nome}: ${eur(r.total)} · ${r.n} mov.${r.percentagem ? ` · ${r.percentagem.replace(".", ",")} %` : ""}`)}
            onMouseLeave={() => setTip(null)}
            onClick={action}
            onKeyDown={action ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); action(); } } : undefined}
          >
            <div className="hbar-label" title={r.nome}>
              {r.nome}
            </div>
            <div className="hbar-track">
              <div className={`hbar-fill${r.categoria_id === null ? " muted" : ""}${r.folded ? " folded" : ""}`} style={{ width: `${Math.max(w, 0.5)}%` }} />
            </div>
            <div className="hbar-value">
              {eur(r.total)} <span className="hbar-pct">{share(toCents(r.total))}</span>
              {action && <span className="hbar-go" aria-hidden="true">{r.folded ? "▾" : "›"}</span>}
            </div>
          </div>
        );
      })}
      {expanded && rest.length > 0 && (
        <button className="link" onClick={() => setExpanded(false)}>Mostrar menos</button>
      )}
      <div className="tip-line" aria-live="polite">
        {tip ?? (onPick ? "Clique numa categoria para ver os movimentos." : "\u00a0")}
      </div>
    </div>
  );
}

/** Eixo com passos «redondos» (1, 2, 5 × 10ⁿ) em cêntimos, incluindo 0; no máx. ~6 marcas. */
export function niceTicks(minC: number, maxC: number, target = 6): number[] {
  const lo = Math.min(0, minC), hi = Math.max(0, maxC);
  if (hi - lo <= 0) return [0, 10000];
  const raw = (hi - lo) / target;
  const p = 10 ** Math.floor(Math.log10(raw));
  const step = ([1, 2, 5, 10].map((m) => m * p).find((s) => s >= raw) ?? 10 * p);
  const start = Math.floor(lo / step) * step, end = Math.ceil(hi / step) * step;
  const out: number[] = [];
  for (let v = start; v <= end + step / 2; v += step) out.push(Math.round(v));
  return out;
}
const axis = (c: number) => Math.round(c / 100).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");

/** Receitas vs despesas (barras agrupadas, 1 eixo) + linha do saldo líquido. Legenda sempre visível. */
export function PeriodChart({ periodos: meses, titulo, parcialEm }: { periodos: PeriodItem[]; titulo: string; parcialEm?: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const W = 720, H = 300, L = 56, R = 76, T = 16, B = 34;
  const iw = W - L - R, ih = H - T - B;
  // O último mês com dados (ainda incompleto: o salário entra no fim do mês anterior e a transferência para
  // investir sai no início) não mostra poupança, senão aparece sempre negativa.
  const parcial = (m: PeriodItem) => m.periodo === parcialEm;
  const vals = meses.flatMap((m) => [toCents(m.despesas), toCents(m.receitas), ...(parcial(m) ? [] : [toCents(m.poupanca)])]);
  const ticks = niceTicks(Math.min(0, ...vals), Math.max(0, ...vals));
  const bottom = ticks[0], top = ticks[ticks.length - 1];
  const y = (c: number) => T + ih - ((c - bottom) / (top - bottom)) * ih;
  const band = iw / Math.max(meses.length, 1);
  const bw = Math.min(24, band / 3);
  const gap = 2;
  const x0 = (i: number) => L + band * i + band / 2;
  const bar = (cx: number, c: number) => {
    const y1 = y(Math.max(c, 0)), y0 = y(0), h = Math.max(y0 - y1, 0);
    const r = Math.min(4, h);
    return h === 0 ? "" : `M${cx},${y0} V${y1 + r} Q${cx},${y1} ${cx + r},${y1} H${cx + bw - r} Q${cx + bw},${y1} ${cx + bw},${y1 + r} V${y0} Z`;
  };
  const has = (m: PeriodItem) => toCents(m.receitas) !== 0 || toCents(m.despesas) !== 0;
  let line = "";
  meses.forEach((m, i) => {
    if (!has(m) || parcial(m)) return;
    line += `${i > 0 && has(meses[i - 1]) ? "L" : "M"}${x0(i)},${y(toCents(m.poupanca))} `;
  });
  const lastIdx = meses.map((m) => has(m) && !parcial(m)).lastIndexOf(true);
  const last = lastIdx >= 0 ? meses[lastIdx] : undefined;
  return (
    <div className="chart-wrap">
      <div className="chart-head">
        <ul className="legend" aria-label="Legenda">
          <li><span className="sw s1" /> Receitas</li>
          <li><span className="sw s2" /> Despesas</li>
          <li><span className="sw s3 line" /> Poupança</li>
        </ul>
        <button className="link" onClick={() => setTable(!table)}>{table ? "Ver gráfico" : "Ver tabela"}</button>
      </div>
      {table ? (
        <table className="data">
          <thead><tr><th>Período</th><th className="num">Receitas</th><th className="num">Despesas</th><th className="num">Poupança</th><th className="num">Saldo no fim</th></tr></thead>
          <tbody>
            {meses.map((m) => (
              <tr key={m.periodo}><td>{mesPt(m.periodo)}</td><td className="num">{eur(m.receitas)}</td><td className="num">{eur(m.despesas)}</td><td className="num">{parcial(m) ? "—" : eur(m.poupanca)}</td><td className="num">{eur(m.saldo_fim)}</td></tr>
            ))}
          </tbody>
        </table>
      ) : (
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={titulo} className="chart">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} className={t === 0 ? "baseline" : "grid"} />
              <text x={L - 8} y={y(t) + 4} textAnchor="end" className="axis-text">{axis(t)}</text>
            </g>
          ))}
          {meses.map((m, i) => (
            <g key={m.periodo}>
              <path d={bar(x0(i) - bw - gap / 2, toCents(m.receitas))} className="s1" />
              <path d={bar(x0(i) + gap / 2, toCents(m.despesas))} className="s2" />
              <text x={x0(i)} y={H - 12} textAnchor="middle" className="axis-text">{tickLabel(m.periodo, i === 0)}</text>
            </g>
          ))}
          <path d={line} className="net-line" fill="none" />
          {meses.map((m, i) => has(m) && !parcial(m) && (
            <circle key={m.periodo} cx={x0(i)} cy={y(toCents(m.poupanca))} r={4} className="net-dot" />
          ))}
          {last && <text x={x0(lastIdx) + 10} y={y(toCents(last.poupanca)) + 4} className="end-label">{eur(last.poupanca)}</text>}
          {meses.map((m, i) => (
            <rect key={m.periodo} x={L + band * i} y={T} width={band} height={ih} fill="transparent"
              onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} />
          ))}
        </svg>
      )}
      {!table && hover !== null && (
        <div className="tooltip" style={{ left: `${(x0(hover) / W) * 100}%` }}>
          <strong>{mesPt(meses[hover].periodo)}</strong>
          <div>Receitas {eur(meses[hover].receitas)}</div>
          <div>Despesas {eur(meses[hover].despesas)}</div>
          {!parcial(meses[hover]) && <div>Poupança {eur(meses[hover].poupanca)}</div>}
          <div>Saldo no fim {eur(meses[hover].saldo_fim)}</div>
        </div>
      )}
    </div>
  );
}
