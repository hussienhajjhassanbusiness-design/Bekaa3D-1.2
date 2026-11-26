import type { ReactNode } from "react";
import Link from "next/link";
import { Icon } from "@/components/ui/Icon";

// #ADMIN-UI (redesign Batch 10)
//
// Presentation-only building blocks shared by the admin detail, form and
// action screens (replacing identical page-local Section / Row / Field
// helpers): a white §43-style card section named by its visible h2, label /
// value rows and stacked facts with mono labels, and a back link. They own
// no data, state or behaviour.

export const ADMIN_LINK_CLASSES =
  "font-semibold text-primary underline underline-offset-2 hover:text-primary-container";

export const ADMIN_LABEL_CLASSES = "font-label text-label-sm uppercase text-on-surface-variant";

export interface AdminSectionProps {
  title: string;
  children: ReactNode;
  description?: ReactNode;
  // "danger": financial / irreversible operations, set apart with an error
  // rule (DESIGN-SYSTEM §10: destructive actions isolated).
  tone?: "default" | "danger";
}

export function AdminSection({ title, children, description, tone = "default" }: AdminSectionProps) {
  return (
    <section
      aria-label={title}
      className={`flex min-w-0 flex-col gap-4 rounded-card border bg-surface-container-lowest p-5 shadow-sm tablet:p-6 ${
        tone === "danger" ? "border-error/30 border-t-4 border-t-error" : "border-outline-variant/40"
      }`}
    >
      <div>
        <h2 className="font-headline text-headline-md text-on-surface">{title}</h2>
        {description && <div className="mt-1 font-body text-body-md text-on-surface-variant">{description}</div>}
      </div>
      {children}
    </section>
  );
}

// One label / value row inside a <dl> (value right-aligned; `breakAll` for
// long opaque ids and references).
export function AdminRow({
  label,
  children,
  breakAll = false,
}: {
  label: string;
  children: ReactNode;
  breakAll?: boolean;
}) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-outline-variant/30 pb-2 last:border-b-0 last:pb-0">
      <dt className={ADMIN_LABEL_CLASSES}>{label}</dt>
      <dd
        className={`min-w-0 text-right font-body text-body-md text-on-surface ${breakAll ? "break-all" : "break-words"}`}
      >
        {children}
      </dd>
    </div>
  );
}

// One stacked fact (mono label above the value) inside a <dl>.
export function AdminField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className={ADMIN_LABEL_CLASSES}>{label}</dt>
      <dd className="mt-1 break-words font-body text-body-md text-on-surface">{children}</dd>
    </div>
  );
}

export function AdminBackLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="inline-flex min-h-11 items-center gap-2 font-label text-label-caps uppercase text-primary hover:text-primary-container"
    >
      <Icon name="arrow-back" className="h-4 w-4" />
      {children}
    </Link>
  );
}
