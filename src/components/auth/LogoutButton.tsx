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
import { Icon } from "@/components/ui/Icon";

// Presentation only (Batch 5): "nav" draws the control as the account
// navigation's last item (Stitch §40 bottom section: logout in error ink
// with a leading glyph). Behaviour is identical for both appearances.
const APPEARANCE_CLASSES = {
  default:
    "whitespace-nowrap rounded-sm px-3 py-2 text-left text-body text-text-primary hover:text-brand-dark-green disabled:opacity-60",
  nav:
    "inline-flex min-h-11 w-full items-center gap-3 whitespace-nowrap rounded-lg px-3 text-left text-body-md text-error " +
    "transition-colors duration-200 ease-standard hover:bg-error-container/50 disabled:opacity-60 desktop:px-4 desktop:py-3 motion-reduce:transition-none",
} as const;

export function LogoutButton({
  className = "",
  appearance = "default",
}: {
  className?: string;
  appearance?: keyof typeof APPEARANCE_CLASSES;
}) {
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
      className={`${APPEARANCE_CLASSES[appearance]} ${className}`}
    >
      {appearance === "nav" && <Icon name="logout" className="h-5 w-5" />}
      {isLoggingOut ? "Logging out…" : "Log out"}
    </button>
  );
}
