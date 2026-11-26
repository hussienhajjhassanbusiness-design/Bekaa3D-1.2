"use client";

import type { ReactNode } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { getQueryClient } from "./queryClient";

// FVS001-T11: the provider only wires QueryClientProvider up to
// getQueryClient()'s safe server/browser client — no props beyond children,
// no auth/toast/error-boundary awareness. Deliberately not integrated into
// src/app/layout.tsx yet; that composition belongs to FVS001-T14.
//
// Calling getQueryClient() directly in the render body (not via useState)
// matches TanStack's current official Next.js App Router guidance: useState
// initialization can be discarded if React suspends before a boundary below
// this provider, whereas getQueryClient()'s own module-scoped
// browserQueryClient already guarantees a stable instance in the browser.
export function QueryProvider({ children }: { children: ReactNode }) {
  const queryClient = getQueryClient();
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
