import { useId, useState, type InputHTMLAttributes } from "react";

export interface PasswordFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "id" | "type"> {
  label: string;
  hint?: string;
  error?: string;
}

// FVS002-T04 — mirrors TextField's structural pattern (label, useId,
// hint/error both linkable via aria-describedby simultaneously) rather than
// wrapping <TextField> as a black box, since the show/hide toggle button
// needs to sit alongside the input inside the same field group. `hint` also
// serves as the password-strength/help-hint slot (§8 of the plan) — no
// separate prop, and deliberately no specific rule copy hardcoded here: the
// backend's real password rules are unconfirmed, so any wording is this
// field's *consumer*'s decision, not this primitive's.
export function PasswordField({ label, hint, error, className, ...rest }: PasswordFieldProps) {
  const [isVisible, setIsVisible] = useState(false);
  const inputId = useId();
  const hintId = useId();
  const errorId = useId();

  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;

  return (
    <div>
      <label htmlFor={inputId} className="block text-label font-semibold uppercase tracking-label text-text-primary">
        {label}
      </label>
      <div className="mt-1 flex items-stretch gap-2">
        <input
          id={inputId}
          type={isVisible ? "text" : "password"}
          aria-describedby={describedBy}
          aria-invalid={error ? true : undefined}
          className={`w-full rounded-sm border px-3 py-2 text-body text-text-primary ${
            error ? "border-danger" : "border-border-default"
          } ${className ?? ""}`}
          {...rest}
        />
        <button
          type="button"
          aria-pressed={isVisible}
          onClick={() => setIsVisible((visible) => !visible)}
          className="shrink-0 rounded-sm border border-border-default px-3 text-body text-text-secondary"
        >
          {isVisible ? "Hide password" : "Show password"}
        </button>
      </div>
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
