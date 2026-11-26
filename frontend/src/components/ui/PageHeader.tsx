import type { ReactNode, Ref } from "react";

export interface PageHeaderProps {
  title: string;
  // Optional mono eyebrow above the title (e.g. the section name).
  eyebrow?: string;
  description?: ReactNode;
  // Right-aligned on wide screens, stacked under the text on narrow ones.
  // Put the primary action last (rightmost).
  actions?: ReactNode;
  // Status/meta rendered in the SAME parent as the h1 (order/offer detail
  // pages read status via `heading level 1 → parent`).
  meta?: ReactNode;
  headingId?: string;
  // Only when the page moves focus to its heading programmatically.
  headingRef?: Ref<HTMLHeadingElement>;
}

// #SHARED-PAGE-HEADER (redesign Batch 5, COMPONENT-SPECS §64)
//
// The app (account/admin) page title block: optional mono eyebrow, the
// page's single h1 in the headline-lg role, muted description, optional
// actions. Layout only — it owns no data, state or business logic.
export function PageHeader({ title, eyebrow, description, actions, meta, headingId, headingRef }: PageHeaderProps) {
  return (
    <div className="mb-8 flex flex-col gap-4 tablet:flex-row tablet:items-end tablet:justify-between">
      <div className="min-w-0 max-w-2xl">
        {eyebrow && <p className="mb-2 font-label text-label-caps uppercase tracking-widest text-primary">{eyebrow}</p>}
        <div className="flex flex-wrap items-center gap-3">
          <h1
            id={headingId}
            ref={headingRef}
            tabIndex={headingRef ? -1 : undefined}
            className="break-words font-headline text-headline-lg text-on-surface"
          >
            {title}
          </h1>
          {meta}
        </div>
        {description && <p className="mt-2 font-body text-body-md text-on-surface-variant">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-3">{actions}</div>}
    </div>
  );
}
