export type StatusBadgeTone = "neutral" | "positive" | "negative" | "warning";

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
const TONE_CLASSES: Record<StatusBadgeTone, string> = {
  neutral: "bg-neutral-100 text-text-primary",
  positive: "bg-success-bg text-success",
  negative: "bg-danger-bg text-danger",
  warning: "bg-warning-bg text-warning-text",
};

export function StatusBadge({ label, tone }: StatusBadgeProps) {
  return (
    <span className={`inline-block rounded-pill px-2 py-0.5 text-caption font-semibold ${TONE_CLASSES[tone]}`}>
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
