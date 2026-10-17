import type { ButtonHTMLAttributes } from "react";

export type ButtonVariant = "primary" | "destructive";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  isLoading?: boolean;
  variant?: ButtonVariant;
}

// FVS002-T02 — a single visual treatment (matching error.tsx's existing
// "Try again" button style) plus a loading/submitting state that disables
// the button and exposes aria-busy, preventing double-submission at the
// component level (Form/T05 and the contract-gated mutations own the rest
// of that guard).
//
// Phase 3 — added `variant="destructive"` (bekaa3d-brand-ui: "destructive
// = solid danger") for admin delete/archive actions. This is a variant
// prop, not a raw className override: appending a conflicting
// `bg-*`/`text-*` utility via `className` would leave the outcome to
// Tailwind's generated stylesheet order rather than call-site order, so a
// second visual treatment is selected here, inside the component, where
// the base classes are never duplicated for the override to race against.
const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: "bg-brand-dark-green text-text-on-brand",
  destructive: "bg-danger text-text-on-brand",
};

export function Button({
  isLoading = false,
  disabled,
  type = "button",
  variant = "primary",
  className,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || isLoading}
      aria-busy={isLoading ? true : undefined}
      className={`rounded-md px-4 py-2 disabled:cursor-not-allowed disabled:opacity-60 ${VARIANT_CLASSES[variant]} ${className ?? ""}`}
      {...rest}
    >
      {children}
    </button>
  );
}
