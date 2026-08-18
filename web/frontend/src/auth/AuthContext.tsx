import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { api } from "../lib/api";

export type Permission =
  | "users.read"
  | "users.manage"
  | "roles.read"
  | "roles.manage"
  | "audit.read";

export type AuthUser = {
  id: string;
  username: string;
  display_name: string;
  is_active: boolean;
  must_change_password: boolean;
  roles: string[];
  permissions: Permission[];
};

type AuthContextValue = {
  user: AuthUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<AuthUser>;
  logout: () => Promise<void>;
  reload: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  async function reload() {
    try {
      const result = await api<{ user: AuthUser }>("/auth/me");
      setUser(result.user);
    } catch {
      setUser(null);
    }
  }

  useEffect(() => {
    void api<{ user: AuthUser }>("/auth/me")
      .then((result) => setUser(result.user))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  async function login(username: string, password: string) {
    const result = await api<{ user: AuthUser }>(
      "/auth/login",
      { method: "POST", body: JSON.stringify({ username, password }) },
      false,
    );
    setUser(result.user);
    return result.user;
  }

  async function logout() {
    try {
      await api("/auth/logout", { method: "POST" }, false);
    } finally {
      setUser(null);
    }
  }

  const value = { user, loading, login, logout, reload };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
