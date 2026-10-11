import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, errorStatus, TOKEN_KEY } from "@/lib/api";

const REFRESH_KEY = "aegis.refresh_token";
let refreshing: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  const rt = sessionStorage.getItem(REFRESH_KEY);
  if (!rt) return false;
  refreshing = refreshing ?? api.post<{ access_token: string; refresh_token: string }>("/auth/refresh", { refresh_token: rt })
    .then((r) => { sessionStorage.setItem(TOKEN_KEY, r.data.access_token); sessionStorage.setItem(REFRESH_KEY, r.data.refresh_token); return true; })
    .catch(() => false).finally(() => { setTimeout(() => { refreshing = null; }, 0); });
  return refreshing;
}
import type { User } from "@/lib/types";

interface AuthState {
  user: User | null | false;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  can: (permission: string) => boolean;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null | false>(null);

  useEffect(() => {
    const h = new URLSearchParams(window.location.hash.slice(1));
    if (h.get("access_token")) {
      sessionStorage.setItem(TOKEN_KEY, h.get("access_token") as string);
      sessionStorage.setItem(REFRESH_KEY, h.get("refresh_token") ?? "");
      window.history.replaceState(null, "", window.location.pathname);
    }
    if (!sessionStorage.getItem(TOKEN_KEY)) {
      setUser(false);
      return;
    }
    api.get<User>("/auth/me").then((r) => setUser(r.data)).catch(() => {
      sessionStorage.removeItem(TOKEN_KEY);
      setUser(false);
    });
  }, []);

  useEffect(() => {
    const id = api.interceptors.response.use(undefined, async (err) => {
      const url = String(err.config?.url);
      if (errorStatus(err) === 401 && !url.includes("/auth/login") && !url.includes("/auth/refresh")) {
        if (!err.config._retried && (await tryRefresh())) {
          err.config._retried = true;
          return api.request(err.config);
        }
        sessionStorage.removeItem(TOKEN_KEY);
        sessionStorage.removeItem(REFRESH_KEY);
        setUser(false);
      }
      return Promise.reject(err);
    });
    return () => api.interceptors.response.eject(id);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const { data } = await api.post<{ access_token: string; refresh_token: string; user: User }>("/auth/login", { email, password });
    sessionStorage.setItem(TOKEN_KEY, data.access_token);
    sessionStorage.setItem(REFRESH_KEY, data.refresh_token);
    setUser(data.user);
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } catch {
      /* token may already be invalid */
    }
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(REFRESH_KEY);
    setUser(false);
  }, []);

  const can = useCallback((p: string) => !!user && user.permissions.includes(p), [user]);
  const value = useMemo(() => ({ user, login, logout, can }), [user, login, logout, can]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
