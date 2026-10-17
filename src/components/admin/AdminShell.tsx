"use client";

// #PHASE3-ADMIN-SHELL
//
// Mirrors AccountLayout's pattern exactly: wraps the one real guard
// (AdminGuard, never a second duplicated boundary) and renders the
// nav + content region only once AdminGuard lets children through.
// Denser spacing than AccountLayout per bekaa3d-brand-ui's admin rule
// ("admin is a tool, not a storefront" — space-2/space-3, neutral
// surfaces, brand color reserved for the active nav item).
import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AdminGuard } from "./AdminGuard";
import { ADMIN_NAV_ITEMS } from "./adminNavItems";

export function AdminShell({ children }: { children: ReactNode }) {
  return (
    <AdminGuard>
      <AdminShellInner>{children}</AdminShellInner>
    </AdminGuard>
  );
}

function AdminShellInner({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex flex-col gap-4 tablet:flex-row">
      <nav
        aria-label="Admin"
        className="flex gap-1 overflow-x-auto tablet:w-48 tablet:flex-col tablet:overflow-visible"
      >
        {ADMIN_NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href || pathname?.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isActive ? "page" : undefined}
              className={`whitespace-nowrap rounded-sm px-3 py-2 text-body ${
                isActive ? "bg-brand-dark-green text-text-on-brand" : "text-text-primary"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
      <section aria-label="Admin content" className="flex-1">
        {children}
      </section>
    </div>
  );
}
