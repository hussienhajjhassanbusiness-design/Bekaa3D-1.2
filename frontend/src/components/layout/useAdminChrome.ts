"use client";

import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth/AuthProvider";

// #ADMIN-CHROME-SWITCH (redesign Batch 9, decision D5)
//
// True only when a signed-in administrator is on an /admin route: then the
// admin shell owns the page chrome and the storefront header, footer and
// floating WhatsApp button step aside. Everyone else on /admin (anonymous,
// still loading, a customer about to see the 404) keeps the normal storefront
// chrome, so an admin URL looks exactly like any other unknown page to them.
// Role check only for layout — access control stays with AdminGuard and the
// backend.
export function isAdminPath(pathname: string | null): boolean {
  return pathname === "/admin" || (pathname?.startsWith("/admin/") ?? false);
}

export function useAdminChrome(): boolean {
  const pathname = usePathname();
  const { isAuthenticated, user } = useAuth();
  return isAdminPath(pathname) && isAuthenticated && user?.role === "admin";
}
