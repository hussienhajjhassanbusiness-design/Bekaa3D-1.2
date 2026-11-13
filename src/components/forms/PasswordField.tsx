import {
  FIELD_ERROR_CLASSES,
  FIELD_HINT_CLASSES,
  FIELD_LABEL_CLASSES,
  FIELD_LEADING_ICON_CLASSES,
  FieldErrorIcon,
  fieldControlClasses,
} from "./fieldStyles";
import { Icon, type IconName } from "@/components/ui/Icon";
import { useId, useState, type InputHTMLAttributes, type Ref } from "react";

export interface PasswordFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "id" | "type"> {
  label: string;
  hint?: string;
  error?: string;
  // Presentation only (Batch 4): decorative icon inside the control (Stitch
  // login's `lock`). The toggle and accessible name are unchanged.
  leadingIcon?: IconName;
  // React 19 passes `ref` to plain function components as a regular prop
  // (no forwardRef wrapper needed) — declared explicitly here so RHF's
  // register()/setFocus (FVS002-T08) can reach the real <input> node. It
  // flows through the existing `...rest` spread onto <input> below exactly
  // like any other native prop; no implementation change was needed.
  ref?: Ref<HTMLInputElement>;
}

// FVS002-T04 — mirrors TextField's structural pattern (label, useId,
// hint/error both linkable via aria-describedby simultaneously) rather than
// wrapping <TextField> as a black box, since the show/hide toggle button
// needs to sit alongside the input inside the same field group. `hint` also
// serves as the password-strength/help-hint slot (§8 of the plan) — no
// separate prop, and deliberately no specific rule copy hardcoded here: the
// backend's real password rules are unconfirmed, so any wording is this
// field's *consumer*'s decision, not this primitive's.
export function PasswordField({ label, hint, error, leadingIcon, className, ...rest }: PasswordFieldProps) {
  const [isVisible, setIsVisible] = useState(false);
  const inputId = useId();
  const hintId = useId();
  const errorId = useId();

  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;

  return (
    <div>
      <label htmlFor={inputId} className={FIELD_LABEL_CLASSES}>
        {label}
      </label>
      {/* The show/hide toggle sits inside the field box (COMPONENT-SPECS §27
          "trailing action"). Its accessible name is still the visible-to-AT
          text "Show password" / "Hide password", plus aria-pressed. */}
      <div className="relative mt-2">
        {leadingIcon && <Icon name={leadingIcon} className={FIELD_LEADING_ICON_CLASSES} />}
        <input
          id={inputId}
          type={isVisible ? "text" : "password"}
          aria-describedby={describedBy}
          aria-invalid={error ? true : undefined}
          className={`${fieldControlClasses(Boolean(error))} pr-14 ${leadingIcon ? "pl-11" : ""} ${className ?? ""}`}
          {...rest}
        />
        <button
          type="button"
          aria-pressed={isVisible}
          onClick={() => setIsVisible((visible) => !visible)}
          className="absolute right-1 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-control text-on-surface-variant transition-colors duration-200 hover:bg-surface-container-high hover:text-on-surface"
        >
          <Icon name={isVisible ? "visibility-off" : "visibility"} className="h-5 w-5" />
          <span className="sr-only">{isVisible ? "Hide password" : "Show password"}</span>
        </button>
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
