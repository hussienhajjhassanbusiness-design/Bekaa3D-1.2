"use client";

// #FVS006-ACCOUNT-SHELL
//
// The one reusable shell every /account/* page mounts through. Wraps the
// existing ProtectedRoute (never a second, duplicated auth boundary) and
// renders the nav + content region only once ProtectedRoute actually lets
// children through (authenticated, or a genuine auth-query error — see
// ProtectedRoute.tsx's own isError handling). The content region is a
// <section>, never a second <main> — AppLayout already renders the one
// <main> landmark at the root layout for every route.
import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { ACCOUNT_NAV_ITEMS } from "./accountNavItems";

export function AccountLayout({ children }: { children: ReactNode }) {
  return (
    <ProtectedRoute>
      <AccountShell>{children}</AccountShell>
    </ProtectedRoute>
  );
}

function AccountShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex flex-col gap-6 tablet:flex-row">
      <nav aria-label="Account" className="flex gap-2 overflow-x-auto tablet:flex-col tablet:overflow-visible">
        {ACCOUNT_NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isActive ? "page" : undefined}
              className={`whitespace-nowrap rounded-md px-3 py-2 text-body ${
                isActive ? "bg-brand-dark-green text-text-on-brand" : "text-text-primary"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
      <section aria-label="Account content" className="flex-1">
        {children}
      </section>
    </div>
  );
}
