"use client";

import { useId, useState } from "react";
import { Button } from "@/components/forms/Button";
import { DialogShell } from "@/components/feedback/DialogShell";

export interface ManualConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  paymentId: string;
  // Caller-supplied, required, no default — no approved operational-
  // acknowledgment wording exists in this repository
  // (FVS-028-IMPLEMENTATION-PLAN.md §0/T04); inventing one would
  // encode unapproved legal/operational copy.
  acknowledgmentLabel: string;
  // Server-authoritative — this dialog never second-guesses it with
  // a locally-computed allowed-status matrix.
  canManualConfirm: boolean;
  manualConfirmBlockedReason?: string;
  isConfirming?: boolean;
  onConfirm: (paymentId: string, reason: string) => void;
}

// #SECURITY-MANUAL-PAYMENT-CONFIRMATION
//
// Composes DialogShell directly — zero new focus-trap code. Manual
// confirmation can never be one casual click: Confirm stays disabled
// until a non-empty reason AND the acknowledgment checkbox are both
// satisfied, and `canManualConfirm`/`manualConfirmBlockedReason`
// (server-authoritative) are never overridden locally. The reason is
// local component state only — never persisted, logged, or placed in
// a URL. The server remains the final authority regardless of what
// this dialog computes.
export function ManualConfirmDialog({
  open,
  onClose,
  paymentId,
  acknowledgmentLabel,
  canManualConfirm,
  manualConfirmBlockedReason,
  isConfirming = false,
  onConfirm,
}: ManualConfirmDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const [reason, setReason] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);

  const canSubmit = reason.trim().length > 0 && acknowledged && canManualConfirm && !isConfirming;

  return (
    <DialogShell open={open} onClose={onClose} isBusy={isConfirming} labelledBy={titleId} describedBy={descriptionId}>
      <h2 id={titleId} className="text-h3 font-bold text-danger">
        Manually Confirm Payment
      </h2>
      <p id={descriptionId} className="mt-2 text-body text-text-secondary">
        This bypasses normal automated verification. Only use this if you have independently confirmed the payment
        with the provider.
      </p>

      {manualConfirmBlockedReason && (
        <p role="alert" className="mt-2 text-caption text-danger">
          {manualConfirmBlockedReason}
        </p>
      )}

      <label className="mt-4 block text-label font-semibold uppercase tracking-label text-text-primary" htmlFor={`${titleId}-reason`}>
        Reason
      </label>
      <textarea
        id={`${titleId}-reason`}
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        className="mt-1 w-full rounded-sm border border-border-default px-3 py-2 text-body"
      />

      <label className="mt-3 flex items-start gap-2 text-body text-text-primary">
        <input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} />
        {acknowledgmentLabel}
      </label>

      <div className="mt-4 flex justify-end gap-2">
        <Button type="button" onClick={onClose} disabled={isConfirming}>
          Cancel
        </Button>
        <Button type="button" onClick={() => onConfirm(paymentId, reason)} disabled={!canSubmit} isLoading={isConfirming}>
          Confirm
        </Button>
      </div>
    </DialogShell>
  );
}
