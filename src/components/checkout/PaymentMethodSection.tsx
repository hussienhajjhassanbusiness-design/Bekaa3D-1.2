"use client";

import { useId } from "react";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { Icon } from "@/components/ui/Icon";
import { PAYMENT_COPY } from "@/lib/checkout/checkoutCopy";
import type { CashOption } from "@/lib/checkout/checkoutEligibility";
import type { PaymentMethod } from "@/lib/checkout/checkoutTypes";
import { CheckoutStepHeading } from "./CheckoutStepHeading";
import {
  CHOICE_CARD_CLASSES,
  CHOICE_HINT_CLASSES,
  CHOICE_INPUT_CLASSES,
  CHOICE_TITLE_CLASSES,
  FIELD_ERROR_CLASSES,
} from "./choiceCardStyles";

export interface PaymentMethodSectionProps {
  value: PaymentMethod | null;
  onChange: (method: PaymentMethod) => void;
  cash: CashOption;
  error?: string;
  disabled?: boolean;
  // Presentation only (Batch 6): numbered step header.
  step?: number;
  complete?: boolean;
}

// #FVS026-PAYMENT-METHOD
//
// Exactly the backend's PaymentMethod enum: "online" (the server's one
// configured provider; no provider is named or chosen here) and "cash"
// (shown only when public settings enable it, and selectable only when
// every line is physical). The public cash_max_order_total is shown as
// information: the cart has no authoritative total, so the server enforces
// the cap (422 CASH_PAYMENT_LIMIT_REACHED) along with any cash block it
// never reveals (422 CASH_NOT_AVAILABLE).
//
// Redesign Batch 6: Stitch payment option cards (COMPONENT-SPECS §34) as a
// radio group. No card fields, no provider names or logos (the online
// provider is a mock in development/staging); the online option's icon is
// the generic "continues on another page" glyph. An ineligible cash option
// stays legible, is disabled, and says why in text ("Not available" plus
// the reason), never by fading alone.
export function PaymentMethodSection({
  value,
  onChange,
  cash,
  error,
  disabled,
  step = 2,
  complete = false,
}: PaymentMethodSectionProps) {
  const errorId = useId();
  const cashHintId = useId();

  return (
    <fieldset className="min-w-0" disabled={disabled} aria-describedby={error ? errorId : undefined}>
      <CheckoutStepHeading as="legend" step={step} title="Payment" complete={complete} />
      <div className="flex flex-col gap-3">
        <label className={CHOICE_CARD_CLASSES}>
          <input
            type="radio"
            name="payment-method"
            className={CHOICE_INPUT_CLASSES}
            checked={value === "online"}
            onChange={() => onChange("online")}
          />
          <span className="min-w-0 flex-1">
            <span className={CHOICE_TITLE_CLASSES}>{PAYMENT_COPY.onlineLabel}</span>
            <span className={CHOICE_HINT_CLASSES}>{PAYMENT_COPY.onlineHint}</span>
          </span>
          <Icon name="open-in-new" className="h-6 w-6 text-primary" />
        </label>

        {cash.offered && (
          <label className={CHOICE_CARD_CLASSES}>
            <input
              type="radio"
              name="payment-method"
              className={CHOICE_INPUT_CLASSES}
              checked={value === "cash"}
              disabled={!cash.eligible}
              aria-describedby={cashHintId}
              onChange={() => onChange("cash")}
            />
            <span className="min-w-0 flex-1">
              <span className="flex flex-wrap items-center gap-2">
                <span className={CHOICE_TITLE_CLASSES}>{PAYMENT_COPY.cashLabel}</span>
                {!cash.eligible && (
                  <span className="rounded-badge bg-surface-container-highest px-2 py-0.5 font-label text-label-sm font-bold uppercase text-on-surface-variant">
                    Not available
                  </span>
                )}
              </span>
              <span id={cashHintId} className={CHOICE_HINT_CLASSES}>
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
            <Icon name="payments" className={`h-6 w-6 ${cash.eligible ? "text-primary" : "text-outline"}`} />
          </label>
        )}
      </div>
      {error && (
        <p id={errorId} className={FIELD_ERROR_CLASSES}>
          <Icon name="error" className="mt-px h-4 w-4" />
          <span>{error}</span>
        </p>
      )}
    </fieldset>
  );
}
