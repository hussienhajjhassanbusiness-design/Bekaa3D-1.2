"use client";

import type { ReactNode } from "react";
import { useAdminChrome } from "./useAdminChrome";

interface SiteChromeProps {
  header?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
}

// #SITE-CHROME (redesign Batch 9, decision D5)
//
// Storefront pages: the sticky header, the one <main> landmark and the
// footer (unchanged from Batch 2). An administrator on /admin/*: no
// storefront chrome at all — AdminShell renders its own sidebar, top bar and
// the page's single <main id="main-content">, so there is still exactly one
// main landmark and the skip link still lands on the content.
export function SiteChrome({ header, footer, children }: SiteChromeProps) {
  const adminChrome = useAdminChrome();

  if (adminChrome) {
    return <>{children}</>;
  }

  return (
    <>
      {/* Batch 2: the storefront header stays in view (Stitch: fixed 64px
          glass bar). Sticky rather than fixed, so no content offset is
          needed; z-40 keeps it under dialogs, toasts and the skip link (z-50). */}
      <header className="sticky top-0 z-40">{header}</header>
      {/* tabIndex={-1}: makes the landmark a valid, standards-based focus
          target for SkipLink (and any future programmatic focus need)
          without inserting <main> itself into the normal Tab sequence —
          tabIndex={0} would wrongly make it an ordinary tab stop. */}
      <main id="main-content" tabIndex={-1}>
        {children}
      </main>
      <footer>{footer}</footer>
    </>
  );
}
