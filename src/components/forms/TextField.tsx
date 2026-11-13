import { FIELD_ERROR_CLASSES, FIELD_HINT_CLASSES, FIELD_LABEL_CLASSES, FieldErrorIcon, fieldControlClasses } from "./fieldStyles";
import { useId, type InputHTMLAttributes, type Ref } from "react";

export interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "id"> {
  label: string;
  hint?: string;
  error?: string;
  // React 19 passes `ref` to plain function components as a regular prop
  // (no forwardRef wrapper needed) — declared explicitly here so RHF's
  // register()/setFocus (FVS002-T08) can reach the real <input> node. It
  // flows through the existing `...rest` spread onto <input> below exactly
  // like any other native prop; no implementation change was needed.
  ref?: Ref<HTMLInputElement>;
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
      <label htmlFor={inputId} className={FIELD_LABEL_CLASSES}>
        {label}
      </label>
      <input
        id={inputId}
        aria-describedby={describedBy}
        aria-invalid={error ? true : undefined}
        className={`mt-2 ${fieldControlClasses(Boolean(error))} ${className ?? ""}`}
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
