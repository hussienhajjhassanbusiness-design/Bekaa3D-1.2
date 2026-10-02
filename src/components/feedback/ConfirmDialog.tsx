"use client";

import { useEffect, useId, useRef } from "react";
import { Button } from "@/components/forms/Button";

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  isConfirming?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

const FOCUSABLE_SELECTOR = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

// #SHARED-CONFIRM-DIALOG
//
// Generic, reusable confirmation modal — intended as shared infrastructure
// for any future high-impact-action confirmation across the app, not just
// settings. Carries NO setting/business-domain knowledge: no setting key,
// no "accepting-orders" anywhere in this file — the key -> requires-
// confirmation mapping lives entirely in the caller.
//
// Built as a manually-managed accessible dialog (role="dialog",
// aria-modal, a simple Tab focus trap, Escape handling) rather than
// native <dialog>.showModal() — this project's jsdom version does not
// implement showModal/close, which would make the component untestable
// at the unit level despite working in a real browser. This is the same
// pattern most non-native dialog libraries implement internally.
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  isConfirming = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<Element | null>(null);

  useEffect(() => {
    if (open) {
      triggerRef.current = document.activeElement;
    } else if (triggerRef.current instanceof HTMLElement) {
      triggerRef.current.focus();
    }
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        // "Escape closes when safe" — not while a confirm action is in
        // flight, the same invariant Confirm/Cancel's own disabled state
        // already enforces for clicks.
        if (!isConfirming) {
          onCancel();
        }
        return;
      }

      if (event.key === "Tab") {
        const dialog = dialogRef.current;
        if (!dialog) {
          return;
        }
        const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (!first || !last) {
          return;
        }
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, isConfirming, onCancel]);

  if (!open) {
    return null;
  }

  function handleBackdropClick(event: React.MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget && !isConfirming) {
      onCancel();
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50" onClick={handleBackdropClick}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        className="rounded-lg bg-white p-6 shadow-elevation-3"
      >
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
          <Button type="button" onClick={onConfirm} isLoading={isConfirming}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
