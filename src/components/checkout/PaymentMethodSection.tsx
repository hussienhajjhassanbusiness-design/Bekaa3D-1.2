"use client";

import { useId } from "react";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { PAYMENT_COPY } from "@/lib/checkout/checkoutCopy";
import type { CashOption } from "@/lib/checkout/checkoutEligibility";
import type { PaymentMethod } from "@/lib/checkout/checkoutTypes";

export interface PaymentMethodSectionProps {
  value: PaymentMethod | null;
  onChange: (method: PaymentMethod) => void;
  cash: CashOption;
  error?: string;
  disabled?: boolean;
}

const radioRowClass =
  "flex items-start gap-2 rounded-md border border-border-default bg-white p-3 text-body text-text-primary";

// #FVS026-PAYMENT-METHOD
//
// Exactly the backend's PaymentMethod enum: "online" (the server's one
// configured provider; no provider is named or chosen here) and "cash"
// (shown only when public settings enable it, and selectable only when
// every line is physical). The public cash_max_order_total is shown as
// information: the cart has no authoritative total, so the server enforces
// the cap (422 CASH_PAYMENT_LIMIT_REACHED) along with any cash block it
// never reveals (422 CASH_NOT_AVAILABLE).
export function PaymentMethodSection({ value, onChange, cash, error, disabled }: PaymentMethodSectionProps) {
  const errorId = useId();
  const cashHintId = useId();

  return (
    <fieldset disabled={disabled} aria-describedby={error ? errorId : undefined}>
      <legend className="mb-2 text-h4 font-semibold text-text-primary">Payment</legend>
      <div className="flex flex-col gap-2">
        <label className={radioRowClass}>
          <input
            type="radio"
            name="payment-method"
            className="mt-1"
            checked={value === "online"}
            onChange={() => onChange("online")}
          />
          <span>
            <span className="block font-semibold">{PAYMENT_COPY.onlineLabel}</span>
            <span className="block text-caption text-text-secondary">{PAYMENT_COPY.onlineHint}</span>
          </span>
        </label>

        {cash.offered && (
          <label className={`${radioRowClass} ${cash.eligible ? "" : "opacity-70"}`}>
            <input
              type="radio"
              name="payment-method"
              className="mt-1"
              checked={value === "cash"}
              disabled={!cash.eligible}
              aria-describedby={cashHintId}
              onChange={() => onChange("cash")}
            />
            <span>
              <span className="block font-semibold">{PAYMENT_COPY.cashLabel}</span>
              <span id={cashHintId} className="block text-caption text-text-secondary">
                {cash.eligible ? (
                  <>
                    {PAYMENT_COPY.cashHint}
                    {cash.maxTotal && (
                      <>
                        {" "}
                        Available for orders up to{" "}
                        <PriceDisplay amountCents={cash.maxTotal.amountCents} currency={cash.maxTotal.currency} />.
                      </>
                    )}
                  </>
                ) : (
                  PAYMENT_COPY.cashNeedsPhysical
                )}
              </span>
            </span>
          </label>
        )}
      </div>
      {error && (
        <p id={errorId} className="mt-1 text-caption text-danger">
          {error}
        </p>
      )}
    </fieldset>
  );
}
