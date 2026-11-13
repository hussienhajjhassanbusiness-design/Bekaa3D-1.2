import type { ButtonHTMLAttributes, Ref } from "react";

// `primary` / `secondary` / `destructive` are the original public variants
// and keep their meaning. `outline` and `ghost` complete the Stitch
// hierarchy (COMPONENT-SPECS §8, DESIGN-SYSTEM §10).
export type ButtonVariant = "primary" | "secondary" | "outline" | "ghost" | "destructive";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  isLoading?: boolean;
  variant?: ButtonVariant;
  // Optional; omitted = "md", the size every existing call site gets.
  size?: ButtonSize;
  // React 19: a plain prop (as TextAreaField), so a dialog can focus its
  // safe default action on open.
  ref?: Ref<HTMLButtonElement>;
}

// FVS002-T02 — a loading/submitting state disables the button and exposes
// aria-busy, preventing double submission at the component level (Form/T05
// and the contract-gated mutations own the rest of that guard; the checkout
// and payment-retry double-click specs rely on this exact contract).
//
// Variants are selected here, inside the component, never by appending a
// conflicting `bg-*`/`text-*` via `className`: Tailwind resolves conflicts
// by stylesheet order, not call-site order. `className` is for layout only
// (width, margins, self-alignment).
//
// Stitch visual language (DESIGN-SYSTEM §12.9 recommendation): 8px radius,
// JetBrains Mono 12px/600 uppercase label (CSS only — the accessible name
// keeps its source casing), primary #0d631b with a green-tinted shadow and
// hover #2e7d32, press scale .95 (disabled under reduced motion).
// box-shadow is deliberately not transitioned: the focus ring must appear
// instantly, not fade in from the CTA shadow.
// Deviations: a 2px border on every variant so all variants share one
// height; a minimum height (36/44/52px) so the default button meets the
// 44px target size; labels may wrap at narrow widths (16px line height)
// instead of overflowing.
const BASE_CLASSES =
  "inline-flex items-center justify-center gap-2 rounded-control border-2 text-center font-label text-label-caps leading-4 uppercase " +
  "transition-[color,background-color,border-color,transform] duration-200 ease-standard " +
  "enabled:active:scale-95 motion-reduce:transition-none motion-reduce:enabled:active:scale-100 " +
  "disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none";

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: "border-transparent bg-primary text-on-primary shadow-lg shadow-primary/20 enabled:hover:bg-primary-container",
  // Secondary outline (2px primary) — for views with several actions where
  // only one solid primary is allowed.
  secondary: "border-primary bg-transparent text-primary enabled:hover:bg-primary/5",
  // Neutral outline — tertiary actions (Cancel, filters, row actions).
  outline:
    "border-outline-variant bg-surface-container-lowest text-on-surface enabled:hover:border-outline enabled:hover:bg-surface-container-high",
  ghost: "border-transparent bg-transparent text-primary enabled:hover:bg-primary/5",
  destructive: "border-transparent bg-error text-on-error enabled:hover:bg-on-error-container",
};

const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: "min-h-9 px-4 py-1.5",
  md: "min-h-11 px-6 py-2.5",
  lg: "min-h-13 px-8 py-3.5",
};

// Batch 3: the same visual hierarchy for a navigation link (<a>/<Link>) that
// must look like a button (hero and CTA-panel links, sign-in links). Links
// have no :enabled/:disabled state, so those variant prefixes are dropped;
// everything else (radius, label, sizes, press scale, reduced motion) is
// identical to <Button>.
export function buttonLinkClassName(variant: ButtonVariant = "primary", size: ButtonSize = "md"): string {
  return `${BASE_CLASSES} ${SIZE_CLASSES[size]} ${VARIANT_CLASSES[variant]}`
    .replace(/\benabled:/g, "")
    .replace(/\s*disabled:\S+/g, "");
}

function ButtonSpinner() {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      data-testid="button-spinner"
      viewBox="0 0 24 24"
      fill="none"
      className="h-4 w-4 shrink-0 animate-spin motion-reduce:animate-none"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

export function Button({
  isLoading = false,
  disabled,
  type = "button",
  variant = "primary",
  size = "md",
  className,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || isLoading}
      aria-busy={isLoading ? true : undefined}
      className={`${BASE_CLASSES} ${SIZE_CLASSES[size]} ${VARIANT_CLASSES[variant]} ${className ?? ""}`}
      {...rest}
    >
      {/* The label stays rendered while loading, so the accessible name and
          any query by name are unchanged; the spinner is decorative. */}
      {isLoading ? <ButtonSpinner /> : null}
      {children}
    </button>
  );
}
