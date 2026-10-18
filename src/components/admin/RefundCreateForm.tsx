"use client";

import { useState } from "react";
import { MoneyInput } from "@/components/forms/MoneyInput";
import { Button } from "@/components/forms/Button";
import { Alert } from "@/components/feedback/Alert";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { validateRefundLineAmount } from "@/lib/admin/refundCreateModel";
import type { RefundLineCandidate } from "@/lib/admin/refundCreateModel";

export interface RefundCreateFormValues {
  lineAmountsCents: Record<string, number | null>;
}

export interface RefundCreateFormProps {
  orderDisplayId: string;
  lineCandidates: readonly RefundLineCandidate[];
  isSubmitting?: boolean;
  // Server-derived field errors (e.g. an over-refund race rejection),
  // keyed by lineId — never computed by this component
  // (#SECURITY-REFUND-RACE-SERVER-WINS). This component never clamps
  // or resubmits automatically.
  lineErrors?: Record<string, string>;
  onSubmit: (values: RefundCreateFormValues) => void;
}

// #ARCHITECTURE-REFUND-LINE-CEILINGS
//
// Each line is refunded independently via its own MoneyInput against
// its own server-supplied ceiling — never a single order-level
// amount. No shipping row exists: ADR-024 means nothing was ever
// charged for shipping, so there is nothing to refund. Selecting a
// nonzero amount on a line whose candidate is `isDigital` shows a
// plain, non-blocking informational warning — there is no entitlement
// to revoke (ADR-019); an STL line simply becomes refunded like any
// other, and a file already emailed cannot be un-sent. This component
// never mutates anything itself, only surfaces the warning and the
// values to submit.
export function RefundCreateForm({
  orderDisplayId,
  lineCandidates,
  isSubmitting = false,
  lineErrors,
  onSubmit,
}: RefundCreateFormProps) {
  const [amounts, setAmounts] = useState<Record<string, number | null>>({});

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

  const hasInvalidAmount = lineValidations.some((entry) => !entry.validation.ok);
  const hasAnySelection = lineCandidates.some((candidate) => (amountFor(candidate.lineId) ?? 0) > 0);

  function buildValues(): RefundCreateFormValues {
    const lineAmountsCents: Record<string, number | null> = {};
    for (const candidate of lineCandidates) {
      lineAmountsCents[candidate.lineId] = amountFor(candidate.lineId);
    }
    return { lineAmountsCents };
  }

  function handleSubmitClick() {
    onSubmit(buildValues());
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-caption text-text-secondary">Order {orderDisplayId}</p>

      {lineValidations.map(({ candidate, validation }) => {
        const hasDigitalSelection = candidate.isDigital && (amountFor(candidate.lineId) ?? 0) > 0;
        return (
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
            {hasDigitalSelection && (
              <Alert
                variant="warning"
                message="This is a digital item. The file was emailed to the customer and cannot be un-sent; this refund cannot be undone."
              />
            )}
          </div>
        );
      })}

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
    </div>
  );
}
