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
          <h2 id={titleId} className="font-headline text-headline-md text-on-surface">
            {title}
          </h2>
          <div id={descriptionId} className="mt-2 break-words font-body text-body-md text-on-surface-variant">
            {description}
          </div>
        </div>
        {children}
        {error && <Alert variant="error" message={error} />}
        <div className="flex flex-col-reverse gap-3 border-t border-outline-variant/30 pt-4 tablet:flex-row tablet:justify-end">
          <Button type="button" variant="outline" onClick={onClose} disabled={pending} className="w-full tablet:w-auto">
            Back
          </Button>
          <Button
            type="submit"
            variant={destructive ? "destructive" : "primary"}
            isLoading={pending}
            className="w-full tablet:w-auto"
          >
            {confirmLabel}
          </Button>
        </div>
      </form>
    </DialogShell>
  );
}
