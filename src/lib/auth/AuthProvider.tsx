"use client";

// FVS-003-IMPLEMENTATION-PLAN.md §9 (confirmed BATCH 3A) — a thin context
// wrapper around the single `["auth","session"]` TanStack Query. Never a
// second, independently-settable state store: `isAuthenticated`/`user` are
// always derived from the query's own data, not tracked separately.
//
// Deliberately does NOT expose `logout` yet — wiring it requires T09
// (logout mutation + cache clearing), which is deferred to Batch 3B.
// Fabricating a placeholder logout function now was considered and
// rejected (see the plan's own T04 task definition) — a function that
// does nothing, or that throws, is worse than simply not existing yet.
import { createContext, useContext, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { getAuthSessionQueryOptions, type SafeUser } from "./authSession";

export interface AuthContextValue {
  user: SafeUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const query = useQuery(getAuthSessionQueryOptions());
  const user = query.data ?? null;

  const value: AuthContextValue = {
    user,
    isAuthenticated: user !== null,
    isLoading: query.isLoading,
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
