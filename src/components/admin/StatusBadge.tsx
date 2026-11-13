export type StatusBadgeTone = "neutral" | "positive" | "negative" | "warning" | "info";

export interface StatusBadgeProps {
  label: string;
  tone: StatusBadgeTone;
}

// #SHARED-STATUS-BADGE
//
// Generalized (FVS-017-IMPLEMENTATION-PLAN.md T02) from a fixed
// "active"/"deactivated" union to a small `{label, tone}` descriptor —
// `tone` stays a controlled, bounded union (never an arbitrary color
// string), so the component keeps its own type guarantees while
// serving any normalized status domain. Each domain (admin account,
// contact message, future ones) owns its own small "describe" helper
// mapping its own normalized status to `{label, tone}` — never a claim
// about the backend's real enum literal, which stays
// NEEDS BACKEND CONFIRMATION per domain. Status is always conveyed as
// visible text, never by color alone.
//
// Stitch canonical status pill (DESIGN-SYSTEM §9 mapping, §12.13): full
// pill, JetBrains Mono 11px bold uppercase (CSS only — the text node keeps
// its source casing for tests and assistive tech). Every pair is >= 4.5:1.
// `info` (added for the offer "countered" state, Batch 7) is additive.
const TONE_CLASSES: Record<StatusBadgeTone, string> = {
  neutral: "bg-surface-container-highest text-on-surface-variant",
  positive: "bg-secondary-container text-on-secondary-container",
  negative: "bg-error-container text-on-error-container",
  warning: "bg-warning-container text-on-warning-container",
  info: "bg-info-container text-on-info-container",
};

export function StatusBadge({ label, tone }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-3 py-1 font-label text-label-sm font-bold uppercase leading-4 ${TONE_CLASSES[tone]}`}
    >
      {label}
    </span>
  );
}

// FVS-009's own normalized admin-account status union, preserved as-is
// — only the describe step changed shape (a function instead of an
// internal lookup table) so existing callers of this concept keep the
// same two-literal type.
export type AdminAccountStatus = "active" | "deactivated";

export function describeAdminAccountStatus(status: AdminAccountStatus): { label: string; tone: StatusBadgeTone } {
  return status === "active" ? { label: "Active", tone: "positive" } : { label: "Deactivated", tone: "negative" };
}
