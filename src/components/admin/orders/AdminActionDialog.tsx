"use client";

import { useId, type FormEvent, type ReactNode } from "react";
import { Alert } from "@/components/feedback/Alert";
import { DialogShell } from "@/components/feedback/DialogShell";
import { Button } from "@/components/forms/Button";

export interface AdminActionDialogProps {
  open: boolean;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  destructive?: boolean;
  pending: boolean;
  // A server refusal (frontend-owned copy). Entered values are kept.
  error: string | null;
  onConfirm: () => void;
  onClose: () => void;
  children?: ReactNode;
}

// #FVS030-ADMIN-ACTION-DIALOG (phase 5H)
//
// The explicit confirmation every admin order write goes through (line
// transition, cash handover, order cancel). DialogShell owns the focus
// trap / Escape / backdrop (inert while pending). Stays open with the
// server's refusal on failure; the caller closes it only after success.
export function AdminActionDialog({
  open,
  title,
  description,
  confirmLabel,
  destructive = false,
  pending,
  error,
  onConfirm,
  onClose,
  children,
}: AdminActionDialogProps) {
  const titleId = useId();
  const descriptionId = useId();

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!pending) onConfirm();
  }

  return (
    <DialogShell open={open} onClose={onClose} isBusy={pending} labelledBy={titleId} describedBy={descriptionId}>
      <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div>
          <h2 id={titleId} className="text-h3 font-bold text-text-primary">
            {title}
          </h2>
          <div id={descriptionId} className="mt-2 text-body text-text-secondary">
            {description}
          </div>
        </div>
        {children}
        {error && <Alert variant="error" message={error} />}
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose} disabled={pending}>
            Back
          </Button>
          <Button type="submit" variant={destructive ? "destructive" : "primary"} isLoading={pending}>
            {confirmLabel}
          </Button>
        </div>
      </form>
    </DialogShell>
  );
}
