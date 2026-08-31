import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { api, onSessionExpired } from "../api/client";
import type { CurrentUser } from "../api/contracts";
import { checkpointStore } from "../recovery/workflowCheckpoint";
import { sessionVault } from "./sessionVault";
import { tokenVault } from "./tokenVault";

interface AuthContextValue {
  user: CurrentUser | null;
  busy: boolean;
  sessionExpired: boolean;
  sessionExpiresWithinFiveMinutes: boolean;
  oidcAvailable: boolean;
  legacyPasswordAvailable: boolean;
  login(input: { tenant_slug: string; email: string; password: string }): Promise<void>;
  startOidcLogin(returnPath: string): void;
  logout(): Promise<void>;
  hasRole(role: string): boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);
let initialSessionRequest: ReturnType<typeof api.oidcSession> | null = null;

function restoreOidcSession() {
  initialSessionRequest ??= api.oidcSession().finally(() => {
    initialSessionRequest = null;
  });
  return initialSessionRequest;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [busy, setBusy] = useState(true);
  const [sessionExpired, setSessionExpired] = useState(false);
  const [sessionExpiresWithinFiveMinutes, setSessionExpiresWithinFiveMinutes] = useState(false);
  const [oidcAvailable, setOidcAvailable] = useState(false);
  const [legacyPasswordAvailable, setLegacyPasswordAvailable] = useState(false);

  useEffect(() => {
    let active = true;
    restoreOidcSession()
      .then((session) => {
        if (!active) return;
        sessionVault.set(session.csrf_token, session.expiry);
        setUser(session.principal);
        setSessionExpired(false);
        setSessionExpiresWithinFiveMinutes(session.expiry.expires_within_five_minutes);
      })
      .catch(() => {
        if (active) sessionVault.clear();
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    api.authCapabilities().then((capabilities) => {
      if (!active) return;
      setOidcAvailable(capabilities.oidc_enabled);
      setLegacyPasswordAvailable(capabilities.legacy_password_enabled);
      if (!capabilities.legacy_password_enabled) tokenVault.clear();
    }).catch(() => undefined);
    return () => { active = false; };
  }, []);

  useEffect(() => onSessionExpired(() => {
    setUser(null);
    setSessionExpired(true);
    setSessionExpiresWithinFiveMinutes(false);
    queryClient.clear();
  }), [queryClient]);

  useEffect(() => {
    if (!user || !sessionVault.isAuthenticated()) return;
    const updateWarning = () => {
      const expiry = sessionVault.currentExpiry();
      setSessionExpiresWithinFiveMinutes(
        expiry !== null && Date.now() >= Date.parse(expiry.expiry_warning_at),
      );
    };
    updateWarning();
    const timer = window.setInterval(updateWarning, 30_000);
    return () => window.clearInterval(timer);
  }, [user]);

  const login = useCallback(async (input: { tenant_slug: string; email: string; password: string }) => {
    setBusy(true);
    sessionVault.clear();
    try {
      const token = await api.login(input);
      tokenVault.set(token.access_token, token.expires_in);
      const current = await api.me();
      setUser(current);
      setSessionExpired(false);
    } catch (error) {
      tokenVault.clear();
      sessionVault.clear();
      setUser(null);
      throw error;
    } finally {
      setBusy(false);
    }
  }, []);

  const startOidcLogin = useCallback((returnPath: string) => {
    const safeReturnPath = returnPath.startsWith("/") && !returnPath.startsWith("//")
      ? returnPath
      : "/cases";
    window.location.assign(`/auth/oidc/login?return_path=${encodeURIComponent(safeReturnPath)}`);
  }, []);

  const logout = useCallback(async () => {
    if (sessionVault.isAuthenticated()) await api.oidcLogout();
    tokenVault.clear();
    sessionVault.clear();
    checkpointStore.clear();
    queryClient.clear();
    setUser(null);
    setSessionExpired(false);
    setSessionExpiresWithinFiveMinutes(false);
  }, [queryClient]);

  const value = useMemo<AuthContextValue>(() => ({
    user, busy, sessionExpired, sessionExpiresWithinFiveMinutes,
    oidcAvailable, legacyPasswordAvailable,
    login, startOidcLogin, logout,
    hasRole: (role: string) => user?.roles.includes(role) ?? false,
  }), [busy, legacyPasswordAvailable, login, logout, oidcAvailable, sessionExpired, sessionExpiresWithinFiveMinutes, startOidcLogin, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

export function useOptionalAuth(): AuthContextValue | null {
  return useContext(AuthContext);
}
