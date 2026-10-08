"use client";

import { useState } from "react";
import { MoneyInput } from "@/components/forms/MoneyInput";
import { Button } from "@/components/forms/Button";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { validateRefundLineAmount } from "@/lib/admin/refundCreateModel";
import type { RefundLineCandidate, ShippingRefundCandidate } from "@/lib/admin/refundCreateModel";

export interface RefundCreateFormValues {
  lineAmountsCents: Record<string, number | null>;
  shippingAmountCents: number | null;
}

export interface RefundCreateFormProps {
  orderDisplayId: string;
  lineCandidates: readonly RefundLineCandidate[];
  shippingCandidate?: ShippingRefundCandidate;
  isSubmitting?: boolean;
  // Server-derived field errors (e.g. an over-refund race rejection),
  // keyed by lineId or "shipping" — never computed by this component
  // (#SECURITY-REFUND-RACE-SERVER-WINS). This component never clamps
  // or resubmits automatically.
  lineErrors?: Record<string, string>;
  onSubmit: (values: RefundCreateFormValues) => void;
}

const SHIPPING_KEY = "shipping";

// #ARCHITECTURE-REFUND-LINE-CEILINGS, #SECURITY-DIGITAL-REFUND-ENTITLEMENT
//
// Each line (and shipping, if supplied) is refunded independently via
// its own MoneyInput against its own server-supplied ceiling — never
// a single order-level amount, and physical lines never imply a
// digital selection. Selecting a nonzero amount on a line whose
// candidate is `isDigital` requires explicit ConfirmDialog
// confirmation before submission, since VS-026 itself states a
// digital refund revokes entitlement — this component only surfaces
// that warning and never mutates entitlement state itself.
export function RefundCreateForm({
  orderDisplayId,
  lineCandidates,
  shippingCandidate,
  isSubmitting = false,
  lineErrors,
  onSubmit,
}: RefundCreateFormProps) {
  const [amounts, setAmounts] = useState<Record<string, number | null>>({});
  const [confirmingDigital, setConfirmingDigital] = useState(false);

  function amountFor(key: string): number | null {
    return amounts[key] ?? null;
  }

  function setAmount(key: string, value: number | null) {
    setAmounts((prev) => ({ ...prev, [key]: value }));
  }

  const lineValidations = lineCandidates.map((candidate) => ({
    candidate,
    validation: validateRefundLineAmount(amountFor(candidate.lineId), candidate.refundableBalanceCents),
  }));
  const shippingValidation = shippingCandidate
    ? validateRefundLineAmount(amountFor(SHIPPING_KEY), shippingCandidate.refundableBalanceCents)
    : null;

  const hasInvalidAmount = lineValidations.some((entry) => !entry.validation.ok) || shippingValidation?.ok === false;
  const hasAnySelection =
    lineCandidates.some((candidate) => (amountFor(candidate.lineId) ?? 0) > 0) || (amountFor(SHIPPING_KEY) ?? 0) > 0;
  const hasDigitalSelection = lineCandidates.some(
    (candidate) => candidate.isDigital && (amountFor(candidate.lineId) ?? 0) > 0
  );

  function buildValues(): RefundCreateFormValues {
    const lineAmountsCents: Record<string, number | null> = {};
    for (const candidate of lineCandidates) {
      lineAmountsCents[candidate.lineId] = amountFor(candidate.lineId);
    }
    return { lineAmountsCents, shippingAmountCents: amountFor(SHIPPING_KEY) };
  }

  function handleSubmitClick() {
    if (hasDigitalSelection) {
      setConfirmingDigital(true);
    } else {
      onSubmit(buildValues());
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-caption text-text-secondary">Order {orderDisplayId}</p>

      {lineValidations.map(({ candidate, validation }) => (
        <div key={candidate.lineId}>
          <p className="text-caption text-text-secondary">
            {candidate.productDisplayName} — refundable:{" "}
            <PriceDisplay amountCents={candidate.refundableBalanceCents} currency={candidate.currency} />
          </p>
          <MoneyInput
            label={`Refund amount for ${candidate.productDisplayName}`}
            currencyLabel={candidate.currency}
            valueCents={amountFor(candidate.lineId)}
            onChangeCents={(next) => setAmount(candidate.lineId, next)}
            error={
              !validation.ok
                ? validation.reason === "exceeds-ceiling"
                  ? "Enter an amount at or below the refundable balance."
                  : "Enter a positive amount."
                : lineErrors?.[candidate.lineId]
            }
          />
        </div>
      ))}

      {shippingCandidate && (
        <div>
          <p className="text-caption text-text-secondary">
            Shipping — refundable:{" "}
            <PriceDisplay amountCents={shippingCandidate.refundableBalanceCents} currency={shippingCandidate.currency} />
          </p>
          <MoneyInput
            label="Shipping refund amount"
            currencyLabel={shippingCandidate.currency}
            valueCents={amountFor(SHIPPING_KEY)}
            onChangeCents={(next) => setAmount(SHIPPING_KEY, next)}
            error={
              shippingValidation && !shippingValidation.ok
                ? shippingValidation.reason === "exceeds-ceiling"
                  ? "Enter an amount at or below the refundable balance."
                  : "Enter a positive amount."
                : lineErrors?.[SHIPPING_KEY]
            }
          />
        </div>
      )}

      <div>
        <Button
          type="button"
          onClick={handleSubmitClick}
          disabled={isSubmitting || hasInvalidAmount || !hasAnySelection}
          isLoading={isSubmitting}
        >
          Submit refund
        </Button>
      </div>

      <ConfirmDialog
        open={confirmingDigital}
        title="Refund includes a digital item"
        description="Refunding this item will revoke the customer's access to the downloadable file. This cannot be undone."
        onConfirm={() => {
          onSubmit(buildValues());
          setConfirmingDigital(false);
        }}
        onCancel={() => setConfirmingDigital(false)}
      />
    </div>
  );
}
