import type { ReactNode } from "react";
import { AccountLayout } from "@/components/account/AccountLayout";

// FVS-006-IMPLEMENTATION-PLAN.md T04 — a thin Next.js layout composing the
// real AccountLayout component, same pattern src/app/layout.tsx already
// uses for AppLayout. Every /account/* route gets the shell + protection
// boundary from here; no page underneath wraps its own second
// ProtectedRoute.
export default function AccountRouteLayout({ children }: { children: ReactNode }) {
  return <AccountLayout>{children}</AccountLayout>;
}
