import { Icon, type IconName } from "@/components/ui/Icon";

export type AlertVariant = "success" | "error" | "warning" | "info";

export interface AlertProps {
  message: string;
  variant: AlertVariant;
}

// FVS002-T02 — persistent page-level feedback, not a transient Toast: no
// dismiss control, ever. Only the urgent "error" variant uses
// role="alert"/aria-live="assertive" — success/info/warning use
// role="status"/aria-live="polite".
//
// Stitch callout (COMPONENT-SPECS §56) with the DESIGN-SYSTEM §9 status
// colours: 12px radius, 1px tinted border, MD3 container background,
// leading icon. The icon is decorative and differs per variant in shape,
// not only colour; the message text always carries the meaning.
const VARIANT_CLASSES: Record<AlertVariant, string> = {
  success: "border-primary/20 bg-secondary-container/40 text-on-surface",
  error: "border-error/20 bg-error-container text-on-error-container",
  warning: "border-warning-outline bg-warning-container text-on-warning-container",
  info: "border-info-outline bg-info-container text-on-info-container",
};

const VARIANT_ICON: Record<AlertVariant, { name: IconName; className: string }> = {
  success: { name: "check-circle", className: "text-primary" },
  error: { name: "error", className: "text-error" },
  warning: { name: "warning", className: "text-on-warning-container" },
  info: { name: "info", className: "text-info" },
};

export function Alert({ message, variant }: AlertProps) {
  const isUrgent = variant === "error";
  const icon = VARIANT_ICON[variant];

  return (
    <div
      role={isUrgent ? "alert" : "status"}
      aria-live={isUrgent ? "assertive" : "polite"}
      className={`flex items-start gap-3 rounded-card border p-4 ${VARIANT_CLASSES[variant]}`}
    >
      <Icon name={icon.name} className={`h-5 w-5 ${icon.className}`} />
      <p className="min-w-0 break-words text-sm">{message}</p>
    </div>
  );
}
