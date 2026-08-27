import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { api, onSessionExpired } from "../api/client";
import type { CurrentUser } from "../api/contracts";
import { checkpointStore } from "../recovery/workflowCheckpoint";
import { tokenVault } from "./tokenVault";

interface AuthContextValue {
  user: CurrentUser | null;
  busy: boolean;
  sessionExpired: boolean;
  login(input: { tenant_slug: string; email: string; password: string }): Promise<void>;
  logout(): void;
  hasRole(role: string): boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [busy, setBusy] = useState(false);
  const [sessionExpired, setSessionExpired] = useState(false);

  useEffect(() => onSessionExpired(() => {
    setUser(null);
    setSessionExpired(true);
    queryClient.clear();
  }), [queryClient]);

  const login = useCallback(async (input: { tenant_slug: string; email: string; password: string }) => {
    setBusy(true);
    try {
      const token = await api.login(input);
      tokenVault.set(token.access_token, token.expires_in);
      const current = await api.me();
      setUser(current);
      setSessionExpired(false);
    } catch (error) {
      tokenVault.clear();
      setUser(null);
      throw error;
    } finally {
      setBusy(false);
    }
  }, []);

  const logout = useCallback(() => {
    tokenVault.clear();
    checkpointStore.clear();
    queryClient.clear();
    setUser(null);
    setSessionExpired(false);
  }, [queryClient]);

  const value = useMemo<AuthContextValue>(() => ({
    user, busy, sessionExpired, login, logout,
    hasRole: (role: string) => user?.roles.includes(role) ?? false,
  }), [busy, login, logout, sessionExpired, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
