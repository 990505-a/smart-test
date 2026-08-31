"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { AuthUser, clearAuth, getStoredUser, getToken, setAuth } from "@/lib/auth";

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  login: async () => {},
  logout: async () => {},
  refresh: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const res = await apiClient.get<AuthUser>("/auth/me");
      setUser(res.data);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Restore from storage instantly, then validate in background
    const stored = getStoredUser();
    if (stored) setUser(stored);
    refresh();
  }, [refresh]);

  const login = useCallback(async (username: string, password: string) => {
    const res = await apiClient.post<{ token: string; user: AuthUser }>(
      "/auth/login",
      { username, password }
    );
    setAuth(res.data.token, res.data.user);
    setUser(res.data.user);
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiClient.post("/auth/logout", {});
    } catch {
      // token may already be invalid — clear locally anyway
    }
    clearAuth();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
