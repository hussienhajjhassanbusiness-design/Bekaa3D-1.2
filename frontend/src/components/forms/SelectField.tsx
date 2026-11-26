import { FIELD_ERROR_CLASSES, FIELD_HINT_CLASSES, FIELD_LABEL_CLASSES, FieldErrorIcon, fieldControlClasses } from "./fieldStyles";
import { Icon } from "@/components/ui/Icon";
import { useId, type ReactNode, type SelectHTMLAttributes } from "react";

export interface SelectFieldProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "id"> {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}

// Mirrors TextField's structural pattern exactly (label/hint/error via
// useId + aria-describedby) so a <select> field looks and behaves like
// every other form control in the admin area — no separate design
// language for dropdowns.
export function SelectField({ label, hint, error, className, children, ...rest }: SelectFieldProps) {
  const selectId = useId();
  const hintId = useId();
  const errorId = useId();

  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;

  return (
    <div>
      <label htmlFor={selectId} className={FIELD_LABEL_CLASSES}>
        {label}
      </label>
      {/* Native <select> kept (keyboard, screen readers, mobile pickers);
          only its arrow is replaced by a decorative chevron. */}
      <div className="relative mt-2">
        <select
          id={selectId}
          aria-describedby={describedBy}
          aria-invalid={error ? true : undefined}
          className={`${fieldControlClasses(Boolean(error))} appearance-none pr-10 ${className ?? ""}`}
          {...rest}
        >
          {children}
        </select>
        <Icon
          name="chevron-down"
          className="pointer-events-none absolute right-3 top-1/2 h-5 w-5 -translate-y-1/2 text-on-surface-variant"
        />
      </div>
      {hint && (
        <p id={hintId} className={FIELD_HINT_CLASSES}>
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className={FIELD_ERROR_CLASSES}>
          <FieldErrorIcon />
          {error}
        </p>
      )}
    </div>
  );
}
