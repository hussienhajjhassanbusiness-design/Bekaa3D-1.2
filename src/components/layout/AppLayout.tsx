import type { ReactNode } from "react";
import { SkipLink } from "./SkipLink";

interface AppLayoutProps {
  header?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
}

export function AppLayout({ header, footer, children }: AppLayoutProps) {
  return (
    <>
      <SkipLink />
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
