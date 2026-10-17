import type { ReactNode } from "react";
import { AdminShell } from "@/components/admin/AdminShell";

// Mirrors src/app/account/layout.tsx's pattern: every /admin/* route
// gets the shell + protection boundary from here; no page underneath
// wraps its own second AdminGuard.
export default function AdminRouteLayout({ children }: { children: ReactNode }) {
  return <AdminShell>{children}</AdminShell>;
}
