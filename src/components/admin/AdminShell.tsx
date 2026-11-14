"use client";

// #PHASE3-ADMIN-SHELL
//
// Wraps the one real guard (AdminGuard, never a second duplicated boundary)
// and renders the admin chrome only once AdminGuard lets children through.
//
// Redesign Batch 9 (PAGE-SPECS D1 shell, COMPONENT-SPECS §40/§41,
// DESIGN-SYSTEM §12.14/§12.15, RESPONSIVE-SPECS "Admin layouts"): the admin
// console is its own app shell — no storefront header/footer (SiteChrome
// steps aside for an administrator on /admin/*). From 1024px a fixed 256px
// sidebar (grouped real routes, active = primary text + right rule) and a
// sticky 64px glass top bar inside the main column. Below 1024px (Stitch has
// no mobile admin) the sidebar becomes a left drawer opened from the top bar,
// built on the shared DialogShell (focus trap, Escape, backdrop, focus
// return) + useSheetBehavior (scroll lock, closes past 1024px); any route
// change closes it. The shell renders the page's single <main
// id="main-content"> (the skip-link target), so the sidebar sits outside it.
import { useCallback, useEffect, useId, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AdminGuard } from "./AdminGuard";
import { ADMIN_NAV_GROUPS, ADMIN_NAV_ITEMS, isAdminNavItemActive } from "./adminNavItems";
import { LogoutButton } from "@/components/auth/LogoutButton";
import { DialogShell } from "@/components/feedback/DialogShell";
import { BrandMark } from "@/components/layout/BrandMark";
import { Icon } from "@/components/ui/Icon";
import { useSheetBehavior } from "@/components/ui/useSheetBehavior";
import { useAuth } from "@/lib/auth/AuthProvider";

const DESKTOP_QUERY = "(min-width: 1024px)";

const subscribeNever = () => () => {};
function useIsClient(): boolean {
  return useSyncExternalStore(
    subscribeNever,
    () => true,
    () => false
  );
}

export function AdminShell({ children }: { children: ReactNode }) {
  return (
    <AdminGuard>
      <AdminShellInner>{children}</AdminShellInner>
    </AdminGuard>
  );
}

function AdminNav({ pathname, onNavigate }: { pathname: string | null; onNavigate?: () => void }) {
  return (
    <nav aria-label="Admin" className="flex-1 overflow-y-auto px-3 pb-4">
      {ADMIN_NAV_GROUPS.map((group) => (
        <div key={group.label} className="pt-4 first:pt-0">
          <p className="px-4 pb-2 font-label text-label-micro uppercase tracking-widest text-on-surface-variant">
            {group.label}
          </p>
          <ul className="flex flex-col gap-0.5">
            {group.items.map((item) => {
              const isActive = isAdminNavItemActive(item, pathname);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={isActive ? "page" : undefined}
                    onClick={onNavigate}
                    className={`flex min-h-11 items-center gap-3 rounded-l-control border-r-4 px-4 py-2 font-body text-body-md transition-colors duration-200 ease-standard motion-reduce:transition-none ${
                      isActive
                        ? "border-primary bg-surface-container-low font-bold text-primary"
                        : "border-transparent text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface"
                    }`}
                  >
                    <Icon name={item.icon} className="h-5 w-5" />
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function SidebarBrand() {
  return (
    <Link href="/admin" className="inline-flex flex-col gap-1 rounded-control">
      <BrandMark />
      <span className="pl-0.5 font-label text-label-sm uppercase tracking-widest text-on-surface-variant">
        Admin console
      </span>
    </Link>
  );
}

function SidebarFooter() {
  return (
    <div className="flex flex-col gap-1 border-t border-outline-variant/40 px-3 pt-4">
      <Link
        href="/"
        className="flex min-h-11 items-center gap-3 rounded-control px-4 py-2 font-body text-body-md text-on-surface-variant transition-colors duration-200 hover:bg-surface-container-high hover:text-on-surface"
      >
        <Icon name="shopping-bag" className="h-5 w-5" />
        View store
      </Link>
      <LogoutButton appearance="nav" />
    </div>
  );
}

function AdminShellInner({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { user } = useAuth();
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [drawerPathname, setDrawerPathname] = useState(pathname);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const drawerTitleId = useId();
  const isClient = useIsClient();

  // Any route change closes the drawer (link clicks, back/forward, redirects).
  if (drawerPathname !== pathname) {
    setDrawerPathname(pathname);
    setIsDrawerOpen(false);
  }

  const closeDrawer = useCallback(() => setIsDrawerOpen(false), []);
  useSheetBehavior({ open: isDrawerOpen, onClose: closeDrawer, closeAtQuery: DESKTOP_QUERY });

  useEffect(() => {
    if (isDrawerOpen) closeButtonRef.current?.focus();
  }, [isDrawerOpen]);

  const current = ADMIN_NAV_ITEMS.find((item) => isAdminNavItemActive(item, pathname));

  return (
    <div className="min-h-dvh bg-blueprint desktop:pl-sidebar">
      {/* Desktop sidebar (≥1024px). */}
      <aside
        aria-label="Admin sidebar"
        className="fixed inset-y-0 left-0 z-30 hidden w-sidebar flex-col border-r border-outline-variant/40 bg-surface pb-6 desktop:flex"
      >
        <div className="flex h-topbar shrink-0 items-center px-6 pt-4">
          <SidebarBrand />
        </div>
        <div className="mt-6 flex min-h-0 flex-1 flex-col">
          <AdminNav pathname={pathname} />
        </div>
        <SidebarFooter />
      </aside>

      <div className="flex min-w-0 flex-col">
        {/* §41 top bar, sticky inside the main column (§12.15). */}
        <header className="sticky top-0 z-20 flex h-topbar items-center gap-3 border-b border-outline-variant/40 bg-surface/80 px-4 backdrop-blur-xl tablet:px-8">
          <button
            type="button"
            onClick={() => setIsDrawerOpen(true)}
            aria-expanded={isDrawerOpen}
            aria-controls="admin-drawer-nav"
            aria-haspopup="dialog"
            aria-label="Open admin menu"
            className="-ml-2 inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-on-surface-variant transition-colors duration-200 hover:bg-surface-container hover:text-primary desktop:hidden"
          >
            <Icon name="menu" />
          </button>
          <div className="min-w-0 flex-1">
            <p className="font-label text-label-micro uppercase tracking-widest text-on-surface-variant">Admin</p>
            <p className="truncate font-headline text-title-sm text-on-surface">{current?.label ?? "Console"}</p>
          </div>
          {user?.email && (
            <p className="hidden min-w-0 max-w-64 items-center gap-2 tablet:flex">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary-fixed text-on-primary-fixed">
                <Icon name="person" className="h-5 w-5" />
              </span>
              <span className="min-w-0">
                <span className="block truncate font-body text-body-md font-semibold text-on-surface">
                  {user.email}
                </span>
                <span className="block font-label text-label-micro uppercase tracking-widest text-on-surface-variant">
                  Administrator
                </span>
              </span>
            </p>
          )}
        </header>

        <main id="main-content" tabIndex={-1} className="min-w-0 flex-1 outline-none">
          <section
            aria-label="Admin content"
            className="mx-auto w-full max-w-content break-words px-4 py-6 tablet:px-8 tablet:py-8 desktop:py-10"
          >
            {children}
          </section>
        </main>
      </div>

      {/* Below 1024px: the same nav in a left drawer, portaled to <body>. */}
      {isClient
        ? createPortal(
            <DialogShell
              open={isDrawerOpen}
              onClose={closeDrawer}
              labelledBy={drawerTitleId}
              panelClassName="fixed inset-y-0 left-0 flex h-dvh w-full max-w-xs flex-col border-r border-outline-variant/40 bg-surface pb-6 shadow-2xl"
            >
              <div className="flex h-topbar shrink-0 items-center justify-between gap-3 border-b border-outline-variant/40 px-4">
                <h2 id={drawerTitleId} className="sr-only">
                  Admin menu
                </h2>
                <SidebarBrand />
                <button
                  ref={closeButtonRef}
                  type="button"
                  onClick={closeDrawer}
                  aria-label="Close admin menu"
                  className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-on-surface-variant transition-colors duration-200 hover:bg-surface-container hover:text-primary"
                >
                  <Icon name="close" />
                </button>
              </div>
              <div id="admin-drawer-nav" className="flex min-h-0 flex-1 flex-col pt-4">
                <AdminNav pathname={pathname} onNavigate={closeDrawer} />
              </div>
              <SidebarFooter />
            </DialogShell>,
            document.body
          )
        : null}
    </div>
  );
}
