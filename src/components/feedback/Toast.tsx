"use client";

import { useEffect, useState } from "react";

export type ToastVariant = "success" | "error" | "info";

export interface ToastProps {
  message: string;
  variant: ToastVariant;
  onDismiss?: () => void;
}

// FRONTEND-VERTICAL-SLICE-PLAN.md §17/§21, bekaa3d-brand-ui tokens.md §2 —
// the "error" variant maps onto the existing "danger" semantic token family
// (tokens.md has no separate "error" token; "danger" already carries that
// meaning). The public variant name stays "error" per T12's required set;
// only this lookup bridges it to the real token names. Full class strings
// are used (not interpolated) so Tailwind's static scanner can find them —
// a template-literal fragment like `bg-${token}-bg` would never make it
// into the compiled CSS.
const VARIANT_CLASSES: Record<ToastVariant, string> = {
  success: "bg-success-bg border-l-success",
  error: "bg-danger-bg border-l-danger",
  info: "bg-info-bg border-l-info",
};

export function Toast({ message, variant, onDismiss }: ToastProps) {
  const [isVisible, setIsVisible] = useState(false);

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
      className={`flex items-center gap-3 rounded-md border-l-4 p-4 text-text-primary shadow-elevation-2 transition-opacity duration-200 motion-reduce:transition-none motion-reduce:duration-0 ${
        isVisible ? "opacity-100" : "opacity-0"
      } ${VARIANT_CLASSES[variant]}`}
    >
      <p className="text-body">{message}</p>
      {onDismiss && (
        <button type="button" aria-label="Dismiss notification" onClick={onDismiss} className="text-text-secondary">
          <span aria-hidden="true">×</span>
        </button>
      )}
    </div>
  );
}
