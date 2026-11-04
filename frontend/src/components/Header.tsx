import { useEffect, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useAsync } from "../hooks";
import { APP } from "../lib/about";
import Logo from "./Logo";

const CONFIG_PATHS = ["/categorias", "/regras", "/contas"];

/** Cabeçalho: Visualizar · Trabalho · Configurações (menu). Em ecrãs pequenos recolhe num botão de menu. */
export default function Header() {
  const { user, logout } = useAuth();
  const loc = useLocation();
  const [menu, setMenu] = useState(false); // menu móvel
  const [cfg, setCfg] = useState(false); // menu «Configurações»
  const cfgRef = useRef<HTMLDivElement>(null);
  const pend = useAsync(() => api.get<{ total: number }>("/api/transactions", { sem_categoria: true, page_size: 1 }), [loc.pathname]);
  const n = pend.data?.total ?? 0;
  const cfgActive = CONFIG_PATHS.some((p) => loc.pathname.startsWith(p));

  useEffect(() => { setMenu(false); setCfg(false); }, [loc.pathname]);
  useEffect(() => {
    if (!cfg) return;
    const outside = (e: MouseEvent) => { if (!cfgRef.current?.contains(e.target as Node)) setCfg(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setCfg(false); };
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", outside); document.removeEventListener("keydown", esc); };
  }, [cfg]);

  return (
    <header className="topbar">
      <div className="topbar-in">
        <NavLink to="/" end className="brand" aria-label={`${APP.nome}: início`}>
          <Logo />
          <span className="brand-text"><strong>Finanças</strong><small>Pessoais</small></span>
        </NavLink>
        <button className="menu-btn" aria-label="Menu" aria-expanded={menu} onClick={() => setMenu(!menu)}>{menu ? "✕" : "☰"}</button>
        <nav className={`mainnav${menu ? " open" : ""}`} aria-label="Principal">
          <div className="navgroup">
            <span className="navcap">Visualizar</span>
            <NavLink to="/" end>Dashboard</NavLink>
            <NavLink to="/movimentos">Movimentos</NavLink>
          </div>
          <div className="navgroup">
            <span className="navcap">Trabalho</span>
            <NavLink to="/rever">Por categorizar{n > 0 && <span className="pill" aria-label={`${n} por categorizar`}>{n}</span>}</NavLink>
            <NavLink to="/contas" className={() => ""}>Adicionar conta</NavLink>
            <NavLink to="/importar">Importar</NavLink>
          </div>
          <div className="navgroup dd" ref={cfgRef}>
            <span className="navcap">Configurações</span>
            <button className={`ddbtn${cfgActive ? " active" : ""}`} aria-haspopup="menu" aria-expanded={cfg} onClick={() => setCfg(!cfg)}>
              Configurações <span aria-hidden="true">▾</span>
            </button>
            <div className={`ddmenu${cfg ? " open" : ""}`} role="menu">
              <NavLink to="/categorias" role="menuitem">Categorias</NavLink>
              <NavLink to="/regras" role="menuitem">Regras</NavLink>
              <NavLink to="/contas" role="menuitem">Contas</NavLink>
            </div>
          </div>
        </nav>
        <div className="usermenu">
          <span className="avatar" aria-hidden="true">{(user?.nome ?? "?").slice(0, 1).toUpperCase()}</span>
          <span className="uname">{user?.nome}</span>
          <button className="link" onClick={() => void logout()}>Sair</button>
        </div>
      </div>
    </header>
  );
}
