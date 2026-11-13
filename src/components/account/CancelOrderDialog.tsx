"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Alert } from "@/components/feedback/Alert";
import { DialogShell } from "@/components/feedback/DialogShell";
import { Button } from "@/components/forms/Button";
import { TextAreaField } from "@/components/forms/TextAreaField";
import { Icon } from "@/components/ui/Icon";
import type { OrderDetailModel } from "@/lib/orders/orderModel";

export interface CancelOrderDialogProps {
  open: boolean;
  order: OrderDetailModel;
  pending: boolean;
  error: string | null;
  // The optional reason (<= 500), passed through only when typed.
  onConfirm: (reason: string) => void;
  onClose: () => void;
}

const PAID_STATUSES = new Set(["paid", "partially_refunded"]);
const REASON_MAX = 500;

// #FVS031-CANCEL-DIALOG (phase 5G)
//
// The explicit confirmation for POST /me/orders/{id}/cancel. The effect is
// described in our own words from the server's order state: the backend
// cancels every not-yet-started physical item (FR-09) and never an STL
// file; a paid order's cancelled items are refunded (ADR-043), and the
// refund appears in the Refunds section once the server records it. A
// cash order the customer cancels counts toward the open-cash-order limit
// for 24 hours (ADR-038 d23), so cash may be refused meanwhile ("may": the
// limit is a setting, and the checkout's own 422 never says which). It
// stays open (and keeps its error) on failure; the parent closes it only
// after a confirmed success. Escape/backdrop are inert while pending.
export function CancelOrderDialog({ open, order, pending, error, onConfirm, onClose }: CancelOrderDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const keepRef = useRef<HTMLButtonElement>(null);
  const [reason, setReason] = useState("");

  useEffect(() => {
    if (open) keepRef.current?.focus();
  }, [open]);

  const paid = order.payment !== null && PAID_STATUSES.has(order.payment.status);

  return (
    <DialogShell open={open} onClose={onClose} isBusy={pending} labelledBy={titleId} describedBy={descriptionId}>
      <p aria-hidden="true" className="mb-1 font-label text-label-sm uppercase tracking-widest text-error">
        Order {order.orderNumber}
      </p>
      <h2 id={titleId} className="font-headline text-headline-md text-on-surface">
        Cancel this order?
      </h2>
      <div id={descriptionId} className="mt-3 flex flex-col gap-2 text-body-md text-on-surface-variant">
        <p>The printed items in this order will be cancelled before we start making them. This can&apos;t be undone.</p>
        {order.containsStl && <p>STL files in this order aren&apos;t affected and will still be emailed to you.</p>}
        {paid && <p>You paid online, so the cancelled items will be refunded. The refund will show on this page.</p>}
        {order.paymentMethod === "cash" && !paid && <p>You won&apos;t need to pay for the cancelled items.</p>}
        {order.paymentMethod === "cash" && (
          // Batch 7: kept verbatim and made more prominent, never softened.
          <p className="flex items-start gap-3 rounded-card border border-warning-outline bg-warning-container p-3 text-on-warning-container">
            <Icon name="warning" className="mt-0.5 h-5 w-5 shrink-0" />
            <span className="min-w-0">
              After cancelling, you may not be able to choose cash payment for a new order for 24 hours.
            </span>
          </p>
        )}
      </div>
      <div className="mt-4">
        <TextAreaField
          label="Reason for cancelling (optional)"
          rows={2}
          maxLength={REASON_MAX}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          disabled={pending}
        />
      </div>
      {error && (
        <div className="mt-4">
          <Alert variant="error" message={error} />
        </div>
      )}
      <div className="mt-6 flex flex-col-reverse gap-3 border-t border-outline-variant/30 pt-4 tablet:flex-row tablet:flex-wrap tablet:justify-end">
        <Button ref={keepRef} type="button" variant="outline" onClick={onClose} disabled={pending}>
          Keep my order
        </Button>
        <Button type="button" variant="destructive" onClick={() => onConfirm(reason)} isLoading={pending}>
          Cancel order
        </Button>
      </div>
    </DialogShell>
  );
}
