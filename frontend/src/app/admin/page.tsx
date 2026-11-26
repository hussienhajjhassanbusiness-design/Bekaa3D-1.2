import { redirect } from "next/navigation";

// /admin has no content of its own — mirrors src/app/account/page.tsx's
// pattern. Auth/role protection is owned entirely by
// src/app/admin/layout.tsx (AdminShell/AdminGuard).
export default function AdminIndexPage() {
  redirect("/admin/settings");
}
