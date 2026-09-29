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
      <header>{header}</header>
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
