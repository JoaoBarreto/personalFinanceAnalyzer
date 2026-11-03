import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import Dashboard from "./pages/Dashboard";
import Import from "./pages/Import";
import Login from "./pages/Login";
import Review from "./pages/Review";
import Rules from "./pages/Rules";
import Transactions from "./pages/Transactions";

export default function App() {
  const { user, ready, logout } = useAuth();
  if (!ready) return <p className="muted center">A carregar…</p>;
  if (!user) return <Login />;
  return (
    <>
      <header className="nav">
        <strong className="brand">Finanças</strong>
        <nav>
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/movimentos">Movimentos</NavLink>
          <NavLink to="/rever">Por categorizar</NavLink>
          <NavLink to="/regras">Regras</NavLink>
          <NavLink to="/importar">Importar</NavLink>
        </nav>
        <span className="spacer" />
        <span className="muted">{user.nome}</span>
        <button className="link" onClick={() => void logout()}>Sair</button>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/movimentos" element={<Transactions />} />
          <Route path="/rever" element={<Review />} />
          <Route path="/regras" element={<Rules />} />
          <Route path="/importar" element={<Import />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  );
}
