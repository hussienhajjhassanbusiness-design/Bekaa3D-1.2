"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { HeaderCartLink } from "./HeaderCartLink";

interface NavItem {
  href: string;
  label: string;
}

// Only routes actually mounted in this phase (REAL STOREFRONT INTEGRATION
// — PHASE 1) — never a link to an unbuilt route (smoke.spec.ts's own
// "no dead Shop/BYI/Contact CTA" rule from FVS-001/FVS-022 applied the
// opposite way now that /shop and /about are real: a dead link would be
// just as wrong as a premature one).
const NAV_ITEMS: readonly NavItem[] = [
  { href: "/", label: "Home" },
  { href: "/shop", label: "Shop" },
  { href: "/about", label: "About" },
  { href: "/contact", label: "Contact" },
];

// Content for AppLayout's <header> landmark — not a second <header>
// element. Text/token-based brand treatment only; the real logo asset
// placement is still a deferred content decision, not this slice's job.
//
// Desktop: a plain inline nav. Mobile (bekaa3d-brand-ui breakpoints): a
// disclosure button toggles the same nav list — no separate mobile-only
// link set, no duplicated markup.
export function Header() {
  const pathname = usePathname();
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  return (
    <div className="border-b border-border-default px-4 py-3 tablet:px-6 desktop:px-8">
      <div className="flex items-center justify-between">
        <Link href="/" className="text-h3 font-semibold text-text-primary">
          Bekaa3D
        </Link>

        <nav aria-label="Main" className="hidden tablet:block">
          <ul className="flex items-center gap-6">
            {NAV_ITEMS.map((item) => {
              const isActive = pathname === item.href;
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={isActive ? "page" : undefined}
                    className={
                      isActive
                        ? "border-b-2 border-brand-dark-green pb-1 text-body font-semibold text-brand-dark-green"
                        : "pb-1 text-body text-text-primary hover:text-brand-dark-green"
                    }
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="flex items-center gap-2">
          <HeaderCartLink />
          <button
            type="button"
            onClick={() => setIsMenuOpen((open) => !open)}
            aria-expanded={isMenuOpen}
            aria-controls="mobile-nav"
            aria-label={isMenuOpen ? "Close menu" : "Open menu"}
            className="flex h-10 w-10 items-center justify-center rounded-md border border-border-default tablet:hidden"
          >
            <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
              {isMenuOpen ? (
                <path strokeLinecap="round" d="M6 6l12 12M18 6L6 18" />
              ) : (
                <path strokeLinecap="round" d="M4 7h16M4 12h16M4 17h16" />
              )}
            </svg>
          </button>
        </div>
      </div>

      {isMenuOpen && (
        <nav id="mobile-nav" aria-label="Main" className="tablet:hidden">
          <ul className="mt-3 flex flex-col gap-1 border-t border-border-default pt-3">
            {NAV_ITEMS.map((item) => {
              const isActive = pathname === item.href;
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={isActive ? "page" : undefined}
                    onClick={() => setIsMenuOpen(false)}
                    className={
                      isActive
                        ? "block rounded-sm px-2 py-2 text-body font-semibold text-brand-dark-green"
                        : "block rounded-sm px-2 py-2 text-body text-text-primary"
                    }
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      )}
    </div>
  );
}
