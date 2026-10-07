export type AdminAccountStatus = "active" | "deactivated";

export interface StatusBadgeProps {
  status: AdminAccountStatus;
}

// #SHARED-STATUS-BADGE
//
// A normalized frontend status union — NOT a claim about the backend's
// real enum literal, which is still NEEDS BACKEND CONFIRMATION
// (FVS-009-IMPLEMENTATION-PLAN.md §1). A future API adapter maps whatever
// the backend actually returns into this union; this component never
// talks to the backend directly. Status is always conveyed as visible
// text, never by color alone.
const STATUS_LABELS: Record<AdminAccountStatus, string> = {
  active: "Active",
  deactivated: "Deactivated",
};

const STATUS_CLASSES: Record<AdminAccountStatus, string> = {
  active: "bg-success-bg text-success",
  deactivated: "bg-danger-bg text-danger",
};

export function StatusBadge({ status }: StatusBadgeProps) {
  return (
    <span className={`inline-block rounded-pill px-2 py-0.5 text-caption font-semibold ${STATUS_CLASSES[status]}`}>
      {STATUS_LABELS[status]}
    </span>
  );
}
