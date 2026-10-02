import { redirect } from "next/navigation";

// FVS-006-IMPLEMENTATION-PLAN.md T04 — a static server redirect, no
// client effect: /account has no content of its own, it only ever means
// /account/profile today. Auth protection is owned entirely by
// src/app/account/layout.tsx (ProtectedRoute via AccountLayout) — this
// file performs no auth check of its own.
export default function AccountIndexPage() {
  redirect("/account/profile");
}
