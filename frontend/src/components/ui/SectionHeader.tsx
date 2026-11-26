import type { ReactNode } from "react";

export interface SectionHeaderProps {
  // id of the heading, for the section's aria-labelledby.
  headingId: string;
  title: string;
  eyebrow?: string;
  description?: string;
  // "center": Stitch centred header (COMPONENT-SPECS §10). "split": title
  // left, `action` (e.g. a "View all" link) right.
  align?: "center" | "split";
  action?: ReactNode;
}

// #SHARED-SECTION-HEADER (redesign Batch 3, COMPONENT-SPECS §10)
//
// The storefront section heading: optional mono eyebrow, an h2 in the
// headline-lg role (32px, 24px below 768), optional muted supporting text.
// Always renders a real <h2> so page outlines stay h1 → h2.
export function SectionHeader({ headingId, title, eyebrow, description, align = "center", action }: SectionHeaderProps) {
  const text = (
    <div className={align === "center" ? "mx-auto max-w-2xl text-center" : "max-w-2xl"}>
      {eyebrow && <p className="mb-3 font-label text-label-caps uppercase tracking-widest text-primary">{eyebrow}</p>}
      <h2 id={headingId} className="font-headline text-headline-lg text-on-surface">
        {title}
      </h2>
      {description && <p className="mt-3 font-body text-body-md text-on-surface-variant">{description}</p>}
    </div>
  );

  if (align === "center") {
    return <div className="mb-10 tablet:mb-16">{text}</div>;
  }

  return (
    <div className="mb-8 flex flex-col gap-4 tablet:mb-12 tablet:flex-row tablet:items-end tablet:justify-between">
      {text}
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
