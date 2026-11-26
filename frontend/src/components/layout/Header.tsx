"use client";

import { useCallback, useEffect, useId, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { DialogShell } from "@/components/feedback/DialogShell";
import { Icon } from "@/components/ui/Icon";
import { useSheetBehavior } from "@/components/ui/useSheetBehavior";
import { BrandMark } from "./BrandMark";
import { HeaderAccountLink } from "./HeaderAccountLink";
import { HeaderCartLink } from "./HeaderCartLink";

interface NavItem {
  href: string;
  label: string;
}

// Only routes actually mounted in this phase (REAL STOREFRONT INTEGRATION
// — PHASE 1) — never a link to an unbuilt route (smoke.spec.ts's own
// "no dead Shop/BYI/Contact CTA" rule from FVS-001/FVS-022 applied the
// opposite way now that /shop and /about are real: a dead link would be
// just as wrong as a premature one). Stitch's own link sets ("STL Store",
// "Materials", …) are not used (DESIGN-SYSTEM §12.7).
const NAV_ITEMS: readonly NavItem[] = [
  { href: "/", label: "Home" },
  { href: "/shop", label: "Shop" },
  { href: "/about", label: "About" },
  { href: "/bring-your-idea", label: "Bring your idea" },
  { href: "/contact", label: "Contact" },
];

// false during SSR and hydration, true afterwards: the portal target
// (document.body) only exists in the browser.
const subscribeNever = () => () => {};
function useIsClient(): boolean {
  return useSyncExternalStore(subscribeNever, () => true, () => false);
}

// Same value as the `desktop` breakpoint: the inline nav takes over from here.
const DESKTOP_QUERY = "(min-width: 1024px)";

// Content for AppLayout's <header> landmark — not a second <header>
// element (AppLayout makes that landmark sticky).
//
// Stitch storefront top navigation, recommended canonical (COMPONENT-SPECS
// §1 / DESIGN-SYSTEM §12.5): 64px, glass surface (surface 80% + blur) with
// an outline-variant/30 hairline, content capped at 1440px with 16 / 32 /
// 64px gutters, logo + links on the left, icon actions on the right.
//
// From 1024px: the inline nav. Below 1024px (Stitch has no mobile header, so
// this is derived — RESPONSIVE-SPECS §1): a menu button opens a right-hand
// sheet built on the shared DialogShell (focus trap, Escape, backdrop
// click, focus return), so there is no second modal system. Stitch shows
// its links from 768px, but its sets had four short labels; the app's five
// (incl. "Bring your idea") plus the logo and the labelled auth entry do
// not fit 768px without crowding the gutter, so the sheet covers tablets.
export function Header() {
  const pathname = usePathname();
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [menuPathname, setMenuPathname] = useState(pathname);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const menuTitleId = useId();
  const isClient = useIsClient();

  // Any route change closes the menu (covers link clicks, back/forward and
  // programmatic navigation alike). Adjusting state while rendering is
  // React's documented alternative to a reset-in-effect.
  if (menuPathname !== pathname) {
    setMenuPathname(pathname);
    setIsMenuOpen(false);
  }

  const closeMenu = useCallback(() => setIsMenuOpen(false), []);

  // Scroll lock while open, and close when growing past the breakpoint
  // (no menu button left to return to) — shared with the shop filter drawer.
  useSheetBehavior({ open: isMenuOpen, onClose: closeMenu, closeAtQuery: DESKTOP_QUERY });

  // Focus moves into the sheet; DialogShell returns it to the menu button
  // on close.
  useEffect(() => {
    if (isMenuOpen) closeButtonRef.current?.focus();
  }, [isMenuOpen]);

  return (
    <div className="relative">
      {/* The glass surface lives on its own layer, not on an ancestor of the
          content: backdrop-filter on an ancestor would become the containing
          block for any position:fixed descendant. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 border-b border-outline-variant/30 bg-surface/80 shadow-sm backdrop-blur-xl"
      />
      <div className="relative mx-auto flex h-16 max-w-content items-center gap-4 px-margin-mobile tablet:px-8 desktop:px-margin-desktop">
        <Link href="/" className="shrink-0 rounded-control">
          <BrandMark />
        </Link>

        <nav aria-label="Main" className="hidden desktop:ml-8 desktop:block">
          <ul className="flex items-center gap-8">
            {NAV_ITEMS.map((item) => {
              const isActive = pathname === item.href;
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={isActive ? "page" : undefined}
                    className={`block whitespace-nowrap border-b-2 pb-1 pt-1.5 font-body text-body-md transition-colors duration-200 ${
                      isActive
                        ? "border-primary font-bold text-primary"
                        : "border-transparent text-on-surface-variant hover:text-primary"
                    }`}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="ml-auto flex items-center gap-1 tablet:gap-3">
          <HeaderCartLink />
          <HeaderAccountLink variant="bar" />
          <button
            type="button"
            onClick={() => setIsMenuOpen(true)}
            aria-expanded={isMenuOpen}
            aria-controls="mobile-nav"
            aria-haspopup="dialog"
            aria-label="Open menu"
            className="inline-flex h-10 w-10 items-center justify-center rounded-full text-on-surface-variant transition-colors duration-200 hover:bg-surface-container hover:text-primary desktop:hidden"
          >
            <Icon name="menu" />
          </button>
        </div>
      </div>

      {/* Portaled to <body> so the sheet stacks above everything (the sticky
          header is its own z-40 context). The shell stays mounted while
          closed (it renders nothing) because it restores focus to the menu
          button on the open → closed transition. */}
      {isClient
        ? createPortal(
            <DialogShell
              open={isMenuOpen}
              onClose={closeMenu}
              labelledBy={menuTitleId}
              panelClassName="fixed inset-y-0 right-0 flex h-dvh w-full max-w-sm flex-col overflow-y-auto border-l border-outline-variant/30 bg-surface shadow-2xl"
            >
              <div className="flex h-16 shrink-0 items-center justify-between gap-4 border-b border-outline-variant/30 px-margin-mobile">
                <h2 id={menuTitleId} className="sr-only">
                  Menu
                </h2>
                <BrandMark />
                <button
                  ref={closeButtonRef}
                  type="button"
                  onClick={closeMenu}
                  aria-label="Close menu"
                  className="inline-flex h-10 w-10 items-center justify-center rounded-full text-on-surface-variant transition-colors duration-200 hover:bg-surface-container hover:text-primary"
                >
                  <Icon name="close" />
                </button>
              </div>

              <nav id="mobile-nav" aria-label="Main" className="px-margin-mobile py-4">
                <ul className="flex flex-col gap-1">
                  {NAV_ITEMS.map((item) => {
                    const isActive = pathname === item.href;
                    return (
                      <li key={item.href}>
                        <Link
                          href={item.href}
                          aria-current={isActive ? "page" : undefined}
                          onClick={closeMenu}
                          className={`flex min-h-14 items-center rounded-control px-4 font-body text-body-lg transition-colors duration-200 ${
                            isActive
                              ? "bg-surface-container-low font-bold text-primary"
                              : "text-on-surface hover:bg-surface-container hover:text-primary"
                          }`}
                        >
                          {item.label}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </nav>

              <div className="mt-auto border-t border-outline-variant/30 p-margin-mobile">
                <HeaderAccountLink variant="menu" onNavigate={closeMenu} />
              </div>
            </DialogShell>,
            document.body
          )
        : null}
    </div>
  );
}
