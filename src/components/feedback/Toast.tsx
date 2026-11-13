"use client";

import { useEffect, useState } from "react";
import { Icon, type IconName } from "@/components/ui/Icon";

export type ToastVariant = "success" | "error" | "info";

export interface ToastProps {
  message: string;
  variant: ToastVariant;
  onDismiss?: () => void;
}

// Stitch toast (COMPONENT-SPECS §47): dark inverse surface, 12px radius,
// shadow-2xl, a leading icon. Stitch only designed the success toast; the
// error/info icons follow its recommendation (error icon in
// error-container). The variant is carried by the icon's shape and the
// message text, never by colour alone. Full class strings are used (not
// interpolated) so Tailwind's static scanner finds them.
const VARIANT_ICON: Record<ToastVariant, { name: IconName; className: string }> = {
  success: { name: "check-circle", className: "text-primary-fixed" },
  error: { name: "error", className: "text-error-container" },
  info: { name: "info", className: "text-info-container" },
};

export function Toast({ message, variant, onDismiss }: ToastProps) {
  const [isVisible, setIsVisible] = useState(false);
  const icon = VARIANT_ICON[variant];

  useEffect(() => {
    // Enter transition only. Dismissal (below) removes the toast
    // immediately — there is deliberately no delayed-unmount exit
    // animation, so reduced motion can never leave a toast "stuck"
    // waiting for a transition that was disabled. See the T12 report for
    // why this is the minimal path the task itself sanctions here.
    const raf = requestAnimationFrame(() => setIsVisible(true));
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      data-variant={variant}
      className={`pointer-events-auto flex w-full max-w-md items-center gap-4 rounded-card bg-inverse-surface px-6 py-4 text-inverse-on-surface shadow-2xl transition-opacity duration-300 motion-reduce:transition-none motion-reduce:duration-0 ${
        isVisible ? "opacity-100" : "opacity-0"
      }`}
    >
      <Icon name={icon.name} className={`h-5 w-5 ${icon.className}`} />
      <p className="min-w-0 flex-1 break-words text-body">{message}</p>
      {onDismiss && (
        <button
          type="button"
          aria-label="Dismiss notification"
          onClick={onDismiss}
          className="-mr-2 flex h-8 w-8 shrink-0 items-center justify-center rounded-control text-inverse-on-surface/80 transition-colors duration-200 hover:bg-white/10 hover:text-inverse-on-surface"
        >
          <Icon name="close" className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
