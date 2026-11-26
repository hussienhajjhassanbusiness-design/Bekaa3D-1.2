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
import { LogoutButton } from "@/components/auth/LogoutButton";
import { Container } from "@/components/ui/Container";
import { Icon } from "@/components/ui/Icon";

export function AccountLayout({ children }: { children: ReactNode }) {
  return (
    <ProtectedRoute>
      <AccountShell>{children}</AccountShell>
    </ProtectedRoute>
  );
}

// Batch 5 (Stitch §40 customer sidebar, DESIGN-SYSTEM §12.14): one <nav>,
// two presentations. From 1024px it is a 256px sticky side panel beside the
// content (active item: primary ink, bold, tinted background and a 4px
// right rail). Below 1024px (Stitch has no account design there) the same
// links become a horizontally scrollable tab strip above the content, so
// the nav is never squeezed beside a narrow content column and never
// hidden. The storefront header and footer stay around it.
const NAV_LINK_BASE =
  "inline-flex min-h-11 shrink-0 items-center gap-2 whitespace-nowrap border-b-2 px-3 text-body-md " +
  "transition-colors duration-200 ease-standard motion-reduce:transition-none " +
  "desktop:w-full desktop:gap-3 desktop:rounded-lg desktop:border-b-0 desktop:border-r-4 desktop:px-4 desktop:py-3";
const NAV_LINK_ACTIVE = "border-primary font-bold text-primary desktop:bg-surface-container-low";
const NAV_LINK_IDLE =
  "border-transparent text-on-surface-variant hover:text-primary desktop:hover:bg-surface-container-high desktop:hover:text-on-surface";

function AccountShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <Container className="py-8 tablet:py-12">
      <div className="flex flex-col gap-6 desktop:grid desktop:grid-cols-[var(--spacing-sidebar)_minmax(0,1fr)] desktop:items-start desktop:gap-10">
        <nav
          aria-label="Account"
          className="flex gap-1 overflow-x-auto border-b border-outline-variant/60 p-1 desktop:sticky desktop:top-24 desktop:flex-col desktop:overflow-visible desktop:rounded-panel desktop:border desktop:border-outline-variant/30 desktop:bg-surface-container-lowest desktop:p-4 desktop:shadow-sm"
        >
          <p
            aria-hidden="true"
            className="hidden px-4 pb-3 pt-1 font-label text-label-sm uppercase tracking-widest text-on-surface-variant desktop:block"
          >
            My account
          </p>
          {ACCOUNT_NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={isActive ? "page" : undefined}
                className={`${NAV_LINK_BASE} ${isActive ? NAV_LINK_ACTIVE : NAV_LINK_IDLE}`}
              >
                <Icon name={item.icon} className="h-5 w-5" strokeWidth={isActive ? 2.25 : 1.75} />
                {item.label}
              </Link>
            );
          })}
          <div className="shrink-0 desktop:mt-3 desktop:border-t desktop:border-outline-variant/30 desktop:pt-3">
            <LogoutButton appearance="nav" />
          </div>
        </nav>
        <section aria-label="Account content" className="min-w-0">
          {children}
        </section>
      </div>
    </Container>
  );
}
