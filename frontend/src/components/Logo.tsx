/** Marca da aplicação: barras ascendentes dentro de um quadrado arredondado. */
export default function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" role="img" aria-label="Finanças Pessoais" className="logo">
      <defs>
        <linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#2a78d6" />
          <stop offset="1" stopColor="#1baf7a" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill="url(#lg)" />
      <rect x="7" y="17" width="4.5" height="8" rx="1.5" fill="#fff" opacity=".9" />
      <rect x="13.75" y="12" width="4.5" height="13" rx="1.5" fill="#fff" />
      <rect x="20.5" y="7" width="4.5" height="18" rx="1.5" fill="#fff" opacity=".9" />
    </svg>
  );
}
