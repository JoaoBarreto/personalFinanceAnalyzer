import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import Footer from "./components/Footer";
import Header from "./components/Header";
import About from "./pages/About";
import Accounts from "./pages/Accounts";
import Categories from "./pages/Categories";
import Dashboard from "./pages/Dashboard";
import Import from "./pages/Import";
import Login from "./pages/Login";
import Review from "./pages/Review";
import Rules from "./pages/Rules";
import Transactions from "./pages/Transactions";

export default function App() {
  const { user, ready } = useAuth();
  if (!ready) return <p className="muted center">A carregar…</p>;
  if (!user) return <Login />;
  return (
    <div className="app-shell">
      <Header />
      <main>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/movimentos" element={<Transactions />} />
          <Route path="/rever" element={<Review />} />
          <Route path="/categorias" element={<Categories />} />
          <Route path="/regras" element={<Rules />} />
          <Route path="/importar" element={<Import />} />
          <Route path="/contas" element={<Accounts />} />
          <Route path="/sobre" element={<About />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <Footer />
    </div>
  );
}
