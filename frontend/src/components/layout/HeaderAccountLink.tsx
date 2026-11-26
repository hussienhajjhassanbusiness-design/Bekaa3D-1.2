"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "@/components/ui/Icon";
import { useAuth } from "@/lib/auth/AuthProvider";
import { buildLoginRedirectPath } from "@/lib/auth/returnTo";

export interface HeaderAccountLinkProps {
  // "bar": the header row (icon-only below 768px, icon + label from 768px).
  // "menu": the full-width entry at the foot of the mobile menu sheet.
  variant: "bar" | "menu";
  onNavigate?: () => void;
}

// Auth pages never become a returnTo target: coming back to /login (or the
// register / reset flows) after signing in would be a dead end.
const AUTH_PATH_PREFIXES = ["/login", "/register", "/forgot-password", "/reset-password", "/verify-email"];

function loginHref(pathname: string): string {
  const isAuthPage = AUTH_PATH_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
  // buildLoginRedirectPath only ever embeds an already-validated same-origin
  // path (src/lib/auth/returnTo.ts); "/" is its own safe default.
  return isAuthPage ? "/login" : buildLoginRedirectPath(pathname);
}

const BAR_CLASS =
  "inline-flex h-10 min-w-10 items-center justify-center gap-2 rounded-control text-on-surface-variant transition-colors duration-200 hover:bg-surface-container hover:text-primary tablet:border tablet:border-outline/30 tablet:px-4";
const BAR_ACTIVE_CLASS = "text-primary tablet:border-primary";
const MENU_CLASS =
  "flex min-h-13 w-full items-center justify-center gap-2 rounded-control bg-primary px-6 font-label text-label-caps uppercase text-on-primary shadow-lg shadow-primary/20 transition-colors duration-200 hover:bg-primary-container";

// #BATCH2-HEADER-ACCOUNT-ENTRY (redesign decision D6)
//
// Signed out: "Sign in" to the existing /login route with the safe returnTo
// of the current page. Signed in: "Account" to the existing /account route
// (which redirects to the profile and owns its own protection). No new
// dropdown and no logout here: logout stays where it already lives.
//
// While the session is still resolving, a same-size inert placeholder holds
// the slot so the header never flashes the wrong state or shifts.
export function HeaderAccountLink({ variant, onNavigate }: HeaderAccountLinkProps) {
  const pathname = usePathname();
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return variant === "bar" ? <span aria-hidden="true" className="inline-block h-10 w-10 tablet:w-24" /> : null;
  }

  const signedIn = user !== null;
  const href = signedIn ? "/account" : loginHref(pathname);
  const label = signedIn ? "Account" : "Sign in";
  // Signed in, the whole /account section is "current" (there is no /account
  // page of its own); signed out, only /login itself is the current page.
  const isActive = signedIn ? pathname.startsWith("/account") : pathname === "/login";
  const ariaCurrent = isActive ? (signedIn ? "true" : "page") : undefined;

  if (variant === "menu") {
    return (
      <Link href={href} onClick={onNavigate} aria-current={ariaCurrent} className={MENU_CLASS}>
        <Icon name={signedIn ? "person" : "login"} className="h-5 w-5" />
        {label}
      </Link>
    );
  }

  return (
    <Link
      href={href}
      aria-current={ariaCurrent}
      className={`${BAR_CLASS} ${isActive ? BAR_ACTIVE_CLASS : ""}`}
    >
      <Icon name={signedIn ? "person" : "login"} className="h-6 w-6 tablet:h-5 tablet:w-5" />
      {/* One element at every width: the label is visually hidden below
          768px but always gives the link its accessible name. */}
      <span className="sr-only tablet:not-sr-only tablet:font-label tablet:text-label-caps tablet:uppercase">{label}</span>
    </Link>
  );
}
