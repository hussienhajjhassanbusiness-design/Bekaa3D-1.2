import { Icon } from "@/components/ui/Icon";

// #SHARED-FIELD-STYLES
//
// One Stitch form-control look (COMPONENT-SPECS §27, DESIGN-SYSTEM §12.18)
// shared by TextField, PasswordField, SelectField, TextAreaField and
// MoneyInput, so the five controls can never drift apart. Presentation only:
// every id / htmlFor / aria-describedby / aria-invalid stays in the field
// components themselves.
//
// Deviations from the Stitch source, both for accessibility:
// - Resting border is `outline` (#707a6c, 4.5:1 on white), not
//   `outline-variant` (#bfcaba, 1.7:1): WCAG 1.4.11 needs >=3:1 for a
//   control boundary (BEKAA3D-TOKEN-MIGRATION §1 "Borders").
// - Focus shows the global box-shadow ring (globals.css) plus a primary
//   border, instead of Stitch's faint ring-primary/20 alone.
// Error styling is not designed in Stitch; this follows its recommendation
// (`border-error ring-2 ring-error/20` + 12px error text with an icon).

export const FIELD_LABEL_CLASSES =
  "block font-label text-label-caps leading-4 uppercase text-on-surface-variant";

// No outer margin: the field adds `mt-2` itself (on the control, or on the
// wrapper when the control sits inside one — select chevron, password toggle).
// `mono` (Batch 4): JetBrains Mono with wide tracking for one-time codes
// (the MFA verification step, COMPONENT-SPECS §38 admin card). Chosen here
// rather than by appending a conflicting `font-*` class at the call site,
// because Tailwind resolves same-property conflicts by stylesheet order.
export function fieldControlClasses(hasError: boolean, options: { mono?: boolean } = {}): string {
  return (
    "block w-full min-h-12 rounded-control border bg-surface-container-lowest px-4 py-3 " +
    (options.mono ? "font-label tracking-widest " : "font-body ") +
    "text-body-md text-on-surface placeholder:text-outline " +
    "transition-colors duration-200 ease-standard focus:border-primary " +
    "disabled:cursor-not-allowed disabled:bg-surface-container-low disabled:opacity-50 " +
    (hasError ? "border-error ring-2 ring-error/20" : "border-outline enabled:hover:border-on-surface-variant")
  );
}

export const FIELD_HINT_CLASSES = "mt-2 text-xs text-on-surface-variant";

export const FIELD_ERROR_CLASSES = "mt-2 flex items-start gap-1.5 text-xs text-error";

// Decorative leading icon inside the control (COMPONENT-SPECS §27 "leading
// icon": Stitch login/forgot email and password fields). The control adds
// `pl-11` so typed text clears it; the label still names the field.
export const FIELD_LEADING_ICON_CLASSES =
  "pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-outline";

// Decorative leading icon for an error message — the text is the message.
export function FieldErrorIcon() {
  return <Icon name="error" className="mt-px h-4 w-4" />;
}
