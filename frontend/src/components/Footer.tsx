import { Link } from "react-router-dom";
import { APP } from "../lib/about";
import Logo from "./Logo";

export default function Footer() {
  return (
    <footer className="site-footer">
      <div className="site-footer-in">
        <div className="foot-brand">
          <Logo size={22} />
          <div>
            <strong>{APP.nome}</strong> <span className="muted">v{APP.versao}</span>
            <div className="muted small">{APP.descricao}. Os dados ficam apenas neste servidor.</div>
          </div>
        </div>
        <nav className="foot-links" aria-label="Rodapé">
          <Link to="/sobre">Sobre</Link>
          <a href={APP.repo} target="_blank" rel="noreferrer">Código no GitHub</a>
          <span className="muted">© {APP.ano} {APP.autor}</span>
        </nav>
      </div>
    </footer>
  );
}
