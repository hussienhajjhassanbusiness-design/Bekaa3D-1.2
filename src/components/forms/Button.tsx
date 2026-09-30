import type { ButtonHTMLAttributes } from "react";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  isLoading?: boolean;
}

// FVS002-T02 — only what this slice's forms actually need: a single visual
// treatment (matching error.tsx's existing "Try again" button style) plus a
// loading/submitting state that disables the button and exposes aria-busy,
// preventing double-submission at the component level (Form/T05 and the
// contract-gated mutations own the rest of that guard). No variant prop —
// add one only when a page in this slice genuinely needs a second style.
export function Button({ isLoading = false, disabled, type = "button", className, children, ...rest }: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || isLoading}
      aria-busy={isLoading ? true : undefined}
      className={`rounded-md bg-brand-dark-green px-4 py-2 text-text-on-brand disabled:cursor-not-allowed disabled:opacity-60 ${className ?? ""}`}
      {...rest}
    >
      {children}
    </button>
  );
}
