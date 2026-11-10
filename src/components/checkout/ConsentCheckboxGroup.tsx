"use client";

import { useId } from "react";
import { CONSENT_COPY } from "@/lib/checkout/checkoutCopy";

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
}

// #FVS026-CONSENTS
//
// One checkbox per backend consent boolean, and only those the order
// needs; never one blanket "I agree to everything", never pre-ticked.
// Wording: PENDING LEGAL REVIEW (see checkoutCopy.ts).
export function ConsentCheckboxGroup({
  showDigital,
  showCash,
  values,
  onChange,
  errors,
  disabled,
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
    <fieldset className="flex flex-col gap-3" disabled={disabled}>
      <legend className="mb-2 text-h4 font-semibold text-text-primary">Confirm</legend>
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
      <label className="flex items-start gap-2 text-body text-text-primary">
        <input
          type="checkbox"
          className="mt-1"
          checked={checked}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span>{label}</span>
      </label>
      {error && (
        <p id={errorId} className="ml-6 mt-1 text-caption text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
