import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, setCsrf, type Me } from "./api";

type Ctx = {
  user: Me | null;
  ready: boolean;
  login: (u: string, p: string) => Promise<void>;
  register: (u: string, nome: string, p: string) => Promise<void>;
  logout: () => Promise<void>;
};
const AuthCtx = createContext<Ctx>(null!);
export const useAuth = () => useContext(AuthCtx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    api.get<Me>("/api/auth/me")
      .then((m) => {
        setCsrf(m.csrf_token);
        setUser(m);
      })
      .catch(() => setUser(null))
      .finally(() => setReady(true));
    const off = () => setUser(null);
    window.addEventListener("unauthenticated", off);
    return () => window.removeEventListener("unauthenticated", off);
  }, []);

  const login = async (username: string, password: string) => {
    const m = await api.post<Me>("/api/auth/login", { username, password });
    setCsrf(m.csrf_token);
    setUser(m);
  };
  const register = async (username: string, nome: string, password: string) => {
    const m = await api.post<Me>("/api/auth/register", { username, nome, password });
    setCsrf(m.csrf_token);
    setUser(m);
  };
  const logout = async () => {
    await api.post("/api/auth/logout");
    setUser(null);
  };
  return <AuthCtx.Provider value={{ user, ready, login, register, logout }}>{children}</AuthCtx.Provider>;
}
