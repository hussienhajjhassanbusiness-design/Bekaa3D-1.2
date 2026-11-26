import type { ReactNode } from "react";
import { SkipLink } from "./SkipLink";
import { SiteChrome } from "./SiteChrome";

interface AppLayoutProps {
  header?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
}

// The skip link, then the chrome: storefront header / main / footer, or —
// for an administrator on /admin/* — the admin shell's own chrome
// (SiteChrome, redesign Batch 9).
export function AppLayout({ header, footer, children }: AppLayoutProps) {
  return (
    <>
      <SkipLink />
      <SiteChrome header={header} footer={footer}>
        {children}
      </SiteChrome>
    </>
  );
}
