"use client";

import { useId, useState } from "react";
import { Button } from "@/components/forms/Button";
import { DialogShell } from "@/components/feedback/DialogShell";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";

export interface SettleRefundDialogProps {
  open: boolean;
  onClose: () => void;
  refundId: string;
  amountCents: number;
  currency: string;
  settlementMethodLabel: string;
  // Caller-supplied, required, no default — mirrors
  // ManualConfirmDialog's precedent: no approved operational-
  // acknowledgment wording exists in this repository.
  acknowledgmentLabel: string;
  // Server-authoritative — this dialog never second-guesses it with
  // a locally-computed allowed-status check.
  canSettle: boolean;
  blockedReason?: string;
  isSettling?: boolean;
  onConfirm: (refundId: string) => void;
}

// #SECURITY-SERVER-REFUND-BALANCE-AUTHORITY, #SECURITY-REFUND-SETTLEMENT-SEPARATION
//
// Mirrors ManualConfirmDialog's (FVS-028) DialogShell + explicit-
// acknowledgment pattern exactly (no reason field — VS-026 does not
// mention one for settlement). Confirm stays disabled until the
// acknowledgment is checked AND `canSettle` (server-authoritative)
// is true. This dialog never marks anything settled itself — it only
// calls `onConfirm`; a future mutation's success/refetch is the only
// thing that can change what the caller renders next.
export function SettleRefundDialog({
  open,
  onClose,
  refundId,
  amountCents,
  currency,
  settlementMethodLabel,
  acknowledgmentLabel,
  canSettle,
  blockedReason,
  isSettling = false,
  onConfirm,
}: SettleRefundDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const [acknowledged, setAcknowledged] = useState(false);

  const canSubmit = acknowledged && canSettle && !isSettling;

  return (
    <DialogShell open={open} onClose={onClose} isBusy={isSettling} labelledBy={titleId} describedBy={descriptionId}>
      <h2 id={titleId} className="text-h3 font-bold text-danger">
        Settle refund {refundId}
      </h2>
      <p id={descriptionId} className="mt-2 text-body text-text-secondary">
        <PriceDisplay amountCents={amountCents} currency={currency} /> via <span>{settlementMethodLabel}</span>
      </p>

      {blockedReason && (
        <p role="alert" className="mt-2 text-caption text-danger">
          {blockedReason}
        </p>
      )}

      <label className="mt-4 flex items-start gap-2 text-body text-text-primary">
        <input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} />
        {acknowledgmentLabel}
      </label>

      <div className="mt-4 flex justify-end gap-2">
        <Button type="button" onClick={onClose} disabled={isSettling}>
          Cancel
        </Button>
        <Button type="button" onClick={() => onConfirm(refundId)} disabled={!canSubmit} isLoading={isSettling}>
          Confirm
        </Button>
      </div>
    </DialogShell>
  );
}
