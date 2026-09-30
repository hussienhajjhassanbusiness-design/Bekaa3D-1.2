export type AlertVariant = "success" | "error" | "warning" | "info";

export interface AlertProps {
  message: string;
  variant: AlertVariant;
}

// FVS002-T02 — persistent page-level feedback, not a transient Toast: no
// dismiss control, ever. Reuses the exact left-border + 8%-tint token
// pattern already established by Toast/BackendUnreachableBanner. "error"
// maps onto the existing "danger" semantic token family (tokens.md has no
// separate "error" token), matching Toast's own public-variant naming so
// the two feedback primitives share one vocabulary. Only the urgent
// "error" variant uses role="alert"/aria-live="assertive" — success/info/
// warning use role="status"/aria-live="polite", matching
// BackendUnreachableBanner's own not-ready-vs-unreachable precedent.
const VARIANT_CLASSES: Record<AlertVariant, string> = {
  success: "bg-success-bg border-l-success",
  error: "bg-danger-bg border-l-danger",
  warning: "bg-warning-bg border-l-warning",
  info: "bg-info-bg border-l-info",
};

export function Alert({ message, variant }: AlertProps) {
  const isUrgent = variant === "error";

  return (
    <div
      role={isUrgent ? "alert" : "status"}
      aria-live={isUrgent ? "assertive" : "polite"}
      className={`rounded-md border-l-4 p-4 text-text-primary ${VARIANT_CLASSES[variant]}`}
    >
      <p className="text-body">{message}</p>
    </div>
  );
}
