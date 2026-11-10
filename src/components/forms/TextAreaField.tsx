import { useId, type Ref, type TextareaHTMLAttributes } from "react";

export interface TextAreaFieldProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "id"> {
  label: string;
  hint?: string;
  error?: string;
  // React 19: a plain prop, so RHF's register()/setFocus reach the node.
  ref?: Ref<HTMLTextAreaElement>;
}

// Multi-line sibling of TextField — identical label/hint/error wiring
// (useId + aria-describedby, error linked rather than a second live
// region), so a textarea behaves like every other form control.
export function TextAreaField({ label, hint, error, className, rows = 3, ...rest }: TextAreaFieldProps) {
  const inputId = useId();
  const hintId = useId();
  const errorId = useId();

  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;

  return (
    <div>
      <label htmlFor={inputId} className="block text-label font-semibold uppercase tracking-label text-text-primary">
        {label}
      </label>
      <textarea
        id={inputId}
        rows={rows}
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
