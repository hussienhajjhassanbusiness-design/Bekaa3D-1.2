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
      <label htmlFor={selectId} className="block text-label font-semibold uppercase tracking-label text-text-primary">
        {label}
      </label>
      <select
        id={selectId}
        aria-describedby={describedBy}
        aria-invalid={error ? true : undefined}
        className={`mt-1 w-full rounded-sm border px-3 py-2 text-body text-text-primary ${
          error ? "border-danger" : "border-border-default"
        } ${className ?? ""}`}
        {...rest}
      >
        {children}
      </select>
      {hint && (
        <p id={hintId} className="mt-1 text-caption text-text-secondary">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="mt-1 text-caption text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
