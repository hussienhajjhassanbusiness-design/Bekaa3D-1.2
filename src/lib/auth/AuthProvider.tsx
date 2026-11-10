"use client";

// FVS-003-IMPLEMENTATION-PLAN.md §9/§10/Part F (confirmed BATCH 3A/3B) — a
// thin context wrapper around the single `["auth","session"]` TanStack
// Query. Never a second, independently-settable state store:
// `isAuthenticated`/`user` are always derived from the query's own data,
// not tracked separately. The one justified addition over Batch 3A's
// {user, isAuthenticated, isLoading} is `logout` (T09's mutation, exposed
// here since this is the one place every protected consumer already
// reads auth state from) — never `refreshSession`/`login`/`setUser`/
// `setAuthenticated`/tokens/roles, which stay owned elsewhere.
//
// Cross-tab wiring (T10): subscribes to the generic, opaque
// crossTabSignal for the literal event string "logout" only (never any
// other payload). On receipt: cancels any in-flight auth-session fetch
// before setting the query anonymous — the "smallest deterministic
// guard" against the Tab-A-logout/Tab-B-mid-login race, where a login's
// own invalidateQueries-triggered refetch could otherwise resolve AFTER
// the incoming logout and silently re-authenticate the tab.
// cancelQueries() is TanStack Query's own built-in mechanism for exactly
// this (the same pattern optimistic updates use to stop a racing refetch
// from clobbering a just-applied local value) — no bespoke epoch/
// generation counter was needed. The incoming handler never calls the
// backend again, never re-announces (so it can never loop), and never
// refreshes.
import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getAuthSessionQueryOptions, AUTH_SESSION_QUERY_KEY, type SafeUser } from "./authSession";
import { createCrossTabSignal } from "./crossTabSignal";
import { useLogout, type LogoutResult } from "./useLogout";
import { clearUserScopedQueries } from "./userScopedQueries";

const LOGOUT_EVENT = "logout";

export interface AuthContextValue {
  user: SafeUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  // #ARCHITECTURE-CANONICAL-AUTH-QUERY — true only for a genuine
  // transport/server failure (bootstrapAuthSession re-throws these; see
  // authSession.ts), never for a confirmed-anonymous outcome. Consumers
  // (ProtectedRoute, FVS-006's profile page) use this to show a retryable
  // error instead of treating an unexpected failure as "log this user
  // out" — found and fixed as a real cross-slice defect at FVS-006.
  isError: boolean;
  logout: () => Promise<LogoutResult>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const query = useQuery(getAuthSessionQueryOptions());
  const queryClient = useQueryClient();
  const logoutMutation = useLogout();
  const user = query.data ?? null;

  useEffect(() => {
    const signal = createCrossTabSignal();
    const unsubscribe = signal.subscribe((eventType) => {
      if (eventType !== LOGOUT_EVENT) {
        return;
      }
      queryClient.cancelQueries({ queryKey: AUTH_SESSION_QUERY_KEY });
      queryClient.setQueryData(AUTH_SESSION_QUERY_KEY, null);
      clearUserScopedQueries(queryClient);
    });

    return () => {
      unsubscribe();
      signal.close();
    };
  }, [queryClient]);

  const value: AuthContextValue = {
    user,
    isAuthenticated: user !== null,
    isLoading: query.isLoading,
    isError: query.isError,
    logout: () => logoutMutation.mutateAsync(),
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
