import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api } from "../services/api";
import type { User } from "../types";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName?: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem("netdoctor_user");
    if (stored) {
      try {
        setUser(JSON.parse(stored));
      } catch {
        localStorage.removeItem("netdoctor_user");
      }
    }
    setLoading(false);
  }, []);

  function persist(token: string, u: User) {
    localStorage.setItem("netdoctor_token", token);
    localStorage.setItem("netdoctor_user", JSON.stringify(u));
    setUser(u);
  }

  async function login(email: string, password: string) {
    const res = await api.post("/api/auth/login", { email, password });
    persist(res.data.access_token, res.data.user);
  }

  async function register(email: string, password: string, fullName?: string) {
    const res = await api.post("/api/auth/register", {
      email,
      password,
      full_name: fullName || null,
    });
    persist(res.data.access_token, res.data.user);
  }

  function logout() {
    localStorage.removeItem("netdoctor_token");
    localStorage.removeItem("netdoctor_user");
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
