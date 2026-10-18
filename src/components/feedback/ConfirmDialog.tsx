"use client";

import { useId } from "react";
import { Button } from "@/components/forms/Button";
import { DialogShell } from "./DialogShell";

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  isConfirming?: boolean;
  // Phase 3 — bekaa3d-brand-ui: "destructive = solid danger". Defaults to
  // false so every existing caller (reference-data archive, settings
  // confirmation, etc.) keeps its current primary-green Confirm button
  // unchanged — archive in particular is a deliberate, pre-existing "soft,
  // reversible-sounding" UI choice (see ReferenceDataManager.tsx) even
  // though it's backend-permanent. Only a genuinely irreversible "Delete"
  // action (a product, an image) opts into this.
  isDestructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

// #SHARED-CONFIRM-DIALOG
//
// Generic, reusable confirmation modal — intended as shared infrastructure
// for any future high-impact-action confirmation across the app, not just
// settings. Carries NO setting/business-domain knowledge: no setting key,
// no "accepting-orders" anywhere in this file — the key -> requires-
// confirmation mapping lives entirely in the caller.
//
// The accessible-dialog mechanics (role, aria-modal, focus trap, Escape,
// backdrop click, focus restoration) now live in the shared
// `DialogShell` (`#SHARED-DIALOG-SHELL`) — this component only
// supplies its own title/description/Confirm/Cancel content on top of
// it, so a second dialog elsewhere in the app never needs its own
// independent focus-trap implementation.
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  isConfirming = false,
  isDestructive = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const titleId = useId();
  const descriptionId = useId();

  return (
    <DialogShell open={open} onClose={onCancel} isBusy={isConfirming} labelledBy={titleId} describedBy={descriptionId}>
      <h2 id={titleId} className="text-h3 font-bold text-text-primary">
        {title}
      </h2>
      <p id={descriptionId} className="mt-2 text-body text-text-secondary">
        {description}
      </p>
      <div className="mt-4 flex justify-end gap-2">
        <Button type="button" onClick={onCancel} disabled={isConfirming}>
          {cancelLabel}
        </Button>
        <Button type="button" variant={isDestructive ? "destructive" : "primary"} onClick={onConfirm} isLoading={isConfirming}>
          {confirmLabel}
        </Button>
      </div>
    </DialogShell>
  );
}
