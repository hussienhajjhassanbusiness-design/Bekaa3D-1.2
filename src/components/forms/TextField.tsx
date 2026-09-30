import { useId, type InputHTMLAttributes } from "react";

export interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "id"> {
  label: string;
  hint?: string;
  error?: string;
}

// FVS002-T03 — deliberately React-Hook-Form-agnostic: plain controlled/
// native input props only, no RHF import here. RHF wiring happens where
// this is consumed (Form, T05). Error text carries no role of its own —
// it's linked via aria-describedby only, so it's announced when focus
// reaches the field rather than as a second, redundant live region on top
// of Form's own error-summary announcement (T05).
export function TextField({ label, hint, error, className, ...rest }: TextFieldProps) {
  const inputId = useId();
  const hintId = useId();
  const errorId = useId();

  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;

  return (
    <div>
      <label htmlFor={inputId} className="block text-label font-semibold uppercase tracking-label text-text-primary">
        {label}
      </label>
      <input
        id={inputId}
        aria-describedby={describedBy}
        aria-invalid={error ? true : undefined}
        className={`mt-1 w-full rounded-sm border px-3 py-2 text-body text-text-primary ${
          error ? "border-danger" : "border-border-default"
        } ${className ?? ""}`}
        {...rest}
      />
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
