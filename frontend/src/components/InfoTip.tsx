import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";

/** «?» numa bolinha: abre um overlay curto a explicar como o número é calculado. Rato, toque, teclado (Esc fecha). */
export default function InfoTip({ title, children }: { title: string; children: ReactNode }) {
  const [pinned, setPinned] = useState(false);
  const [hover, setHover] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const open = pinned || hover;
  const pop = useRef<HTMLDivElement>(null);

  // O overlay ancora-se ao «?», mas nunca sai do ecrã: desloca-se para dentro com uma margem de 8 px.
  useLayoutEffect(() => {
    const el = pop.current;
    if (!open || !el) return;
    el.style.left = "0px";
    const r = el.getBoundingClientRect();
    const vw = document.documentElement.clientWidth;
    let dx = 0;
    if (r.right > vw - 8) dx = vw - 8 - r.right;
    if (r.left + dx < 8) dx = 8 - r.left;
    el.style.left = `${dx}px`;
  }, [open]);

  useEffect(() => {
    if (!pinned) return;
    const outside = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setPinned(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") { setPinned(false); setHover(false); } };
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", outside); document.removeEventListener("keydown", esc); };
  }, [pinned]);

  return (
    <span className="infotip" ref={ref} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      <button type="button" className="infotip-btn" aria-label={`Como é calculado: ${title}`} aria-expanded={open}
        onClick={() => setPinned((p) => !p)} onKeyDown={(e) => { if (e.key === "Escape") { setPinned(false); setHover(false); } }}>
        ?
      </button>
      {open && (
        <div className="infotip-pop" role="dialog" aria-label={title} ref={pop}>
          <strong>{title}</strong>
          {children}
        </div>
      )}
    </span>
  );
}
