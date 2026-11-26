import { FIELD_ERROR_CLASSES, FIELD_HINT_CLASSES, FIELD_LABEL_CLASSES, FieldErrorIcon, fieldControlClasses } from "./fieldStyles";
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
      <label htmlFor={inputId} className={FIELD_LABEL_CLASSES}>
        {label}
      </label>
      <textarea
        id={inputId}
        rows={rows}
        aria-describedby={describedBy}
        aria-invalid={error ? true : undefined}
        className={`mt-2 ${fieldControlClasses(Boolean(error))} resize-y ${className ?? ""}`}
        {...rest}
      />
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
