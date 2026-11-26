import type { ElementType, ReactNode } from "react";

export interface ContainerProps {
  children: ReactNode;
  className?: string;
  // The rendered element (div by default; e.g. "section" or "nav").
  as?: ElementType;
}

// #SHARED-CONTAINER (redesign Batch 3, DESIGN-SYSTEM §12.4)
//
// One content width for the public storefront: 1440px cap, centred, with
// the 16px (mobile) / 32px (tablet) / 64px (desktop) gutters the header and
// footer already use. Used by Home, Shop and Product Detail. Vertical
// spacing stays with the caller.
export function Container({ children, className, as: Element = "div" }: ContainerProps) {
  return (
    <Element
      className={`mx-auto w-full max-w-content px-margin-mobile tablet:px-8 desktop:px-margin-desktop ${className ?? ""}`}
    >
      {children}
    </Element>
  );
}
