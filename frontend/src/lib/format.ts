const NBSP = " ";

/** Formata uma string decimal ("-1234.5") como "-1 234,50 €" sem passar por float. */
export function eur(v: string | null | undefined): string {
  if (v == null || v === "") return "—";
  const neg = v.trim().startsWith("-");
  const [int, dec = ""] = v.trim().replace(/^[-+]/, "").split(".");
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
  return `${neg ? "-" : ""}${grouped},${(dec + "00").slice(0, 2)}${NBSP}€`;
}

export function pct(v: string | null | undefined): string {
  return v == null ? "—" : `${v.replace(".", ",")}${NBSP}%`;
}

/** "2026-10-05" -> "05/10/2026" */
export function dataPt(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
/** "2026-10" -> "out 2026"; um ano ("2026") fica como está. */
export function mesPt(ym: string): string {
  const [y, m] = ym.split("-");
  return m ? `${MESES[Number(m) - 1]} ${y}` : y;
}

/** Só o mês, para cabeçalhos de colunas: "2026-10" -> "out". */
export function mesCurto(ym: string): string {
  const m = ym.split("-")[1];
  return m ? MESES[Number(m) - 1] : ym;
}

/** "-12.34" -> -1234 (aritmética em cêntimos inteiros, nunca float para somar dinheiro). */
export function toCents(s: string): number {
  const neg = s.trim().startsWith("-");
  const [i, d = ""] = s.trim().replace(/^[-+]/, "").split(".");
  const v = Number(i) * 100 + Number((d + "00").slice(0, 2));
  return neg ? -v : v;
}

export function fromCents(c: number): string {
  const neg = c < 0;
  const a = Math.abs(c);
  return `${neg ? "-" : ""}${Math.floor(a / 100)}.${String(a % 100).padStart(2, "0")}`;
}
