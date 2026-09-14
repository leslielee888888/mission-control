import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api, configureAuthToken, configureUnauthorizedHandler } from "../api/client";
import type { User } from "../api/types";

const TOKEN_STORAGE_KEY = "mission-control:token";

interface AuthContextValue {
  user: User | null;
  /** "loading": token present, still confirming it with the API.
   * "unauthenticated": no token, or it turned out invalid/expired.
   * "authenticated": token confirmed, `user` is populated. */
  status: "loading" | "authenticated" | "unauthenticated";
  login: (email: string, password: string) => Promise<void>;
  isLoggingIn: boolean;
  loginError: string | null;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_STORAGE_KEY));

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken(null);
    queryClient.clear();
  }, [queryClient]);

  // Deliberately NOT a useEffect: a login (or logout) can swap the tree
  // from <LoginScreen> to the authenticated screens in the same commit,
  // whose queries fire from *their own* mount effects. React runs effects
  // bottom-up (children before parents), so if this ran in a useEffect
  // here, a freshly-mounted child's first fetch could beat this effect and
  // go out with a stale (or no) token. Setting it during render instead —
  // a plain synchronous assignment to a module-level function reference,
  // not a state update — guarantees it's current before any effect in this
  // commit runs.
  configureAuthToken(() => token);
  configureUnauthorizedHandler(logout);

  const whoami = useQuery({
    queryKey: ["auth", "whoami"],
    queryFn: api.auth.whoami,
    enabled: token !== null,
    retry: false,
  });

  // An expired/revoked token: whoami 401s (which also fires logout via
  // configureUnauthorizedHandler above, but that's async — this covers the
  // render before that runs).
  useEffect(() => {
    if (token !== null && whoami.isError) {
      logout();
    }
  }, [token, whoami.isError, logout]);

  const loginMutation = useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) => api.auth.login(email, password),
    onSuccess: (data) => {
      localStorage.setItem(TOKEN_STORAGE_KEY, data.token);
      queryClient.setQueryData(["auth", "whoami"], data.user);
      setToken(data.token);
    },
  });

  const login = useCallback(
    async (email: string, password: string) => {
      await loginMutation.mutateAsync({ email, password });
    },
    [loginMutation],
  );

  const status: AuthContextValue["status"] =
    token === null ? "unauthenticated" : whoami.data ? "authenticated" : "loading";

  const value = useMemo<AuthContextValue>(
    () => ({
      user: whoami.data ?? null,
      status,
      login,
      isLoggingIn: loginMutation.isPending,
      loginError: loginMutation.error instanceof ApiError ? loginMutation.error.message : null,
      logout,
    }),
    [whoami.data, status, login, loginMutation.isPending, loginMutation.error, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
