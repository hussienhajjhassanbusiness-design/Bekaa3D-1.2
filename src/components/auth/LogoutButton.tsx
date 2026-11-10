"use client";

// Phase 5A defect 7 — the one mounted logout control, shared by the
// account shell and the admin shell. It owns no logout logic: it calls
// AuthProvider's logout() (useLogout: local-first clear, cross-tab
// broadcast, real POST /auth/logout, one bounded retry; it always
// resolves, never rejects), then leaves for /login. An explicit logout
// goes to plain /login, never /login?returnTo=…, so signing back in does
// not drop the user onto the page they chose to leave. No server outcome
// is ever shown: the frontend is already logged out locally either way.
//
// Tertiary button (bekaa3d-brand-ui: text-only ink); focus ring comes
// from the global :focus-visible treatment in globals.css.
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth/AuthProvider";

export function LogoutButton({ className = "" }: { className?: string }) {
  const { logout } = useAuth();
  const router = useRouter();
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  async function handleClick() {
    if (isLoggingOut) return;
    setIsLoggingOut(true);
    try {
      await logout();
    } finally {
      router.replace("/login");
    }
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={isLoggingOut}
      aria-busy={isLoggingOut || undefined}
      className={`whitespace-nowrap rounded-sm px-3 py-2 text-left text-body text-text-primary hover:text-brand-dark-green disabled:opacity-60 ${className}`}
    >
      {isLoggingOut ? "Logging out…" : "Log out"}
    </button>
  );
}
