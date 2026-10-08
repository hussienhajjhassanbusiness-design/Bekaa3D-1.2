"use client";

import { useId, useState } from "react";
import { Button } from "@/components/forms/Button";
import { DialogShell } from "@/components/feedback/DialogShell";

export interface AdminCancelDialogProps {
  open: boolean;
  onClose: () => void;
  lineId: string;
  // Caller-supplied only — never computed here
  // (#ARCHITECTURE-REFUND-OBLIGATION-SERVER-OWNED). Absent means no
  // obligation message is known yet, never "no obligation exists".
  refundObligationMessage?: string;
  isCancelling?: boolean;
  onConfirm: (lineId: string, reason: string) => void;
}

// #SECURITY-SERVER-CANCELLATION-AUTHORITY
//
// Mirrors ManualConfirmDialog's (FVS-028) DialogShell + reason-
// textarea pattern — ConfirmDialog cannot cleanly host reason entry,
// so this composes DialogShell directly rather than contorting
// ConfirmDialog's API. Confirm stays disabled until a non-empty
// (post-trim) reason is entered. The reason is local component state
// only — never persisted, logged, or placed in a URL. This dialog
// never second-guesses server-authoritative legality locally and
// never mutates a line's status itself — a future mutation's success
// is the only thing that can change what the caller renders next.
export function AdminCancelDialog({
  open,
  onClose,
  lineId,
  refundObligationMessage,
  isCancelling = false,
  onConfirm,
}: AdminCancelDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const [reason, setReason] = useState("");

  const canSubmit = reason.trim().length > 0 && !isCancelling;

  return (
    <DialogShell open={open} onClose={onClose} isBusy={isCancelling} labelledBy={titleId} describedBy={descriptionId}>
      <h2 id={titleId} className="text-h3 font-bold text-danger">
        Cancel order line
      </h2>
      <p id={descriptionId} className="mt-2 text-body text-text-secondary">
        This cancels this order line. It cannot be undone.
      </p>

      {refundObligationMessage && (
        <p role="alert" className="mt-2 text-caption text-danger">
          {refundObligationMessage}
        </p>
      )}

      <label
        className="mt-4 block text-label font-semibold uppercase tracking-label text-text-primary"
        htmlFor={`${titleId}-reason`}
      >
        Reason
      </label>
      <textarea
        id={`${titleId}-reason`}
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        className="mt-1 w-full rounded-sm border border-border-default px-3 py-2 text-body"
      />

      <div className="mt-4 flex justify-end gap-2">
        <Button type="button" onClick={onClose} disabled={isCancelling}>
          Cancel
        </Button>
        <Button
          type="button"
          onClick={() => onConfirm(lineId, reason.trim())}
          disabled={!canSubmit}
          isLoading={isCancelling}
        >
          Confirm
        </Button>
      </div>
    </DialogShell>
  );
}
