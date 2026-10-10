"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { ApiError, api, getCachedUser, getToken, setCachedUser, setToken } from "./client";

export type Me = {
  id: number;
  name: string;
  email: string;
  role: "employee" | "finance";
  title: string;
  department: string;
  grade: string;
  joined_on: string;
  company: { name: string; currency: string; fx_rates: Record<string, number>; cutoff_day: number };
};

type Ctx = {
  user: Me | null;
  ready: boolean;
  signIn: (email: string, password: string) => Promise<Me>;
  signOut: () => void;
};

const AuthContext = createContext<Ctx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      setReady(true);
      return;
    }
    // Returning visit: render with the user saved at sign-in (no wait), then confirm with the server.
    const saved = getCachedUser<Me>();
    if (saved) {
      setUser(saved);
      setReady(true);
    }
    api<Me>("/auth/me", { timeoutMs: 60000 })
      .then((u) => {
        setUser(u);
        setCachedUser(u);
      })
      .catch((e) => {
        // an expired token signs out (request() handles 401); a network blip keeps a saved session
        if (!saved || (e instanceof ApiError && e.status === 401)) {
          setToken(null);
          setUser(null);
        }
      })
      .finally(() => setReady(true));
  }, []);

  useEffect(() => {
    const out = () => setUser(null);
    window.addEventListener("cvx:signed-out", out);
    return () => window.removeEventListener("cvx:signed-out", out);
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const form = new URLSearchParams({ username: email, password });
    const r = await api<{ access_token: string; user: Me }>("/auth/token", { form, auth: false, timeoutMs: 60000 });
    setToken(r.access_token);
    setCachedUser(r.user);
    setUser(r.user);
    return r.user;
  }, []);

  const signOut = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  return <AuthContext.Provider value={{ user, ready, signIn, signOut }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const c = useContext(AuthContext);
  if (!c) throw new Error("useAuth outside AuthProvider");
  return c;
}
