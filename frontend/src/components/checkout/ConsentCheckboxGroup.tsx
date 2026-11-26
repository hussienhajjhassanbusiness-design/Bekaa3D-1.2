"use client";

import { useId } from "react";
import { Icon } from "@/components/ui/Icon";
import { CONSENT_COPY } from "@/lib/checkout/checkoutCopy";
import { CheckoutStepHeading } from "./CheckoutStepHeading";
import { FIELD_ERROR_CLASSES } from "./choiceCardStyles";

export type ConsentKey = "acceptTerms" | "acceptDigitalFinalSale" | "acceptCashTerms";

export interface ConsentCheckboxGroupProps {
  // An STL line is in the cart (accept_digital_final_sale is required).
  showDigital: boolean;
  // Cash is the chosen payment method (accept_cash_terms is required).
  showCash: boolean;
  values: Readonly<Record<ConsentKey, boolean>>;
  onChange: (key: ConsentKey, checked: boolean) => void;
  errors: Partial<Record<ConsentKey, string>>;
  disabled?: boolean;
  // Presentation only (Batch 6): numbered step header.
  step?: number;
  complete?: boolean;
}

// #FVS026-CONSENTS
//
// One checkbox per backend consent boolean, and only those the order
// needs; never one blanket "I agree to everything", never pre-ticked.
// Wording: PENDING LEGAL REVIEW (see checkoutCopy.ts).
//
// Redesign Batch 6: numbered step header as the legend; each consent is a
// bordered row whose whole surface is the <label> (a 20px native
// checkbox, text wraps freely). Same booleans, same wording, never
// pre-ticked; an error turns the row's border red AND adds text.
export function ConsentCheckboxGroup({
  showDigital,
  showCash,
  values,
  onChange,
  errors,
  disabled,
  step = 3,
  complete = false,
}: ConsentCheckboxGroupProps) {
  const items: { key: ConsentKey; label: string }[] = [
    { key: "acceptTerms", label: CONSENT_COPY.terms },
    ...(showDigital
      ? [
          {
            key: "acceptDigitalFinalSale" as const,
            label: CONSENT_COPY.digitalFinalSale,
          },
        ]
      : []),
    ...(showCash ? [{ key: "acceptCashTerms" as const, label: CONSENT_COPY.cashTerms }] : []),
  ];

  return (
    <fieldset className="flex min-w-0 flex-col gap-3" disabled={disabled}>
      <CheckoutStepHeading as="legend" step={step} title="Confirm" complete={complete} />
      {items.map((item) => (
        <ConsentCheckbox
          key={item.key}
          label={item.label}
          checked={values[item.key]}
          error={errors[item.key]}
          onChange={(checked) => onChange(item.key, checked)}
        />
      ))}
    </fieldset>
  );
}

function ConsentCheckbox({
  label,
  checked,
  error,
  onChange,
}: {
  label: string;
  checked: boolean;
  error?: string;
  onChange: (checked: boolean) => void;
}) {
  const errorId = useId();
  return (
    <div>
      <label
        className={`flex cursor-pointer items-start gap-3 rounded-control border bg-surface-container-lowest p-4 text-body-md text-on-surface transition-colors duration-200 ease-standard hover:bg-surface-container-low has-[:checked]:border-primary has-[:disabled]:cursor-not-allowed motion-reduce:transition-none ${
          error ? "border-error ring-2 ring-error/20" : "border-outline-variant"
        }`}
      >
        <input
          type="checkbox"
          className="mt-0.5 h-5 w-5 shrink-0 cursor-[inherit] accent-primary"
          checked={checked}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span className="min-w-0 break-words">{label}</span>
      </label>
      {error && (
        <p id={errorId} className={FIELD_ERROR_CLASSES}>
          <Icon name="error" className="mt-px h-4 w-4" />
          <span>{error}</span>
        </p>
      )}
    </div>
  );
}
