"use client";

import { useState } from "react";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { Button } from "@/components/forms/Button";
import { MoneyInput } from "@/components/forms/MoneyInput";
import { SelectField } from "@/components/forms/SelectField";
import { TextAreaField } from "@/components/forms/TextAreaField";
import { adminOrdersApi } from "@/lib/admin/orders/adminOrdersApi";
import { canRecordCashHandover, describeCancelReason, orderCancelOffer } from "@/lib/admin/orders/adminOrderPresentation";
import type { AdminOrderDetailDTO, CancelReason } from "@/lib/admin/orders/adminOrderTypes";
import { useAdminOrderWrite } from "@/lib/admin/orders/useAdminOrders";
import { AdminActionDialog } from "./AdminActionDialog";

const NOTE_MAX = 500;

// #FVS030-ORDER-LEVEL-ACTIONS (phase 5H)
//
// Record cash handover (POST …/cash-handover) and Cancel order (POST
// …/cancel), each offered only on the backend's own rule
// (adminOrderPresentation.ts) and confirmed explicitly.
//   - Handover: the administrator TYPES the cash received; it is never
//     prefilled or derived (BR-143), and the server refuses anything but
//     the exact live total (422 CASH_AMOUNT_MISMATCH, with amount_due).
//     Nothing is marked paid here: the server records the payment and
//     marks every live line delivered / picked up.
//   - Cancel: every physical line before shipping or collection; a reason
//     (1-500) is required, and a cancel reason when a ready line takes one.
//     A paid order's cancelled lines are refunded by the server (ADR-043).
type Open = "handover" | "cancel" | null;

export function OrderLevelActions({ order }: { order: AdminOrderDetailDTO }) {
  // Lifted so that a refusal's re-read (which may withdraw the offer) never
  // unmounts an open dialog and its error.
  const [open, setOpen] = useState<Open>(null);
  const handover = canRecordCashHandover(order);
  const cancel = orderCancelOffer(order);
  const showHandover = handover || open === "handover";
  const showCancel = cancel !== null || open === "cancel";
  if (!showHandover && !showCancel) return null;

  return (
    <section aria-label="Order actions" className="flex flex-col gap-3 rounded-md border border-border-default bg-white p-4">
      <h2 className="text-h3 font-bold text-text-primary">Order actions</h2>
      <div className="flex flex-col gap-2 tablet:flex-row tablet:flex-wrap">
        {showHandover && (
          <CashHandover order={order} open={open === "handover"} setOpen={(v) => setOpen(v ? "handover" : null)} />
        )}
        {showCancel && (
          <CancelOrder
            order={order}
            reasons={cancel?.reasons ?? []}
            reasonRequired={cancel?.reasonRequired ?? false}
            open={open === "cancel"}
            setOpen={(v) => setOpen(v ? "cancel" : null)}
          />
        )}
      </div>
    </section>
  );
}

interface DialogControl {
  open: boolean;
  setOpen: (open: boolean) => void;
}

function CashHandover({ order, open, setOpen }: { order: AdminOrderDetailDTO } & DialogControl) {
  const write = useAdminOrderWrite();
  const [cents, setCents] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const [fieldError, setFieldError] = useState<string | undefined>(undefined);
  const due = order.amount_due;

  async function confirm() {
    if (cents === null || cents <= 0) {
      setFieldError("Enter the cash received.");
      return;
    }
    const body = { amount_cents: cents, currency: "USD" as const, ...(note.trim() ? { note: note.trim() } : {}) };
    if (await write.run(() => adminOrdersApi.cashHandover(order.id, body))) setOpen(false);
  }

  return (
    <>
      <Button
        type="button"
        onClick={() => {
          write.reset();
          setCents(null);
          setNote("");
          setFieldError(undefined);
          setOpen(true);
        }}
      >
        Record cash handover
      </Button>
      <AdminActionDialog
        open={open}
        title="Record cash handover?"
        description={
          <p>
            Records the cash the customer paid and marks every live line{" "}
            {order.fulfillment_method === "pickup" ? "picked up" : "delivered"}. Amount due:{" "}
            {due ? <PriceDisplay amountCents={due.amount_cents} currency={due.currency} /> : "unavailable"}.
          </p>
        }
        confirmLabel="Record cash handover"
        pending={write.state.kind === "pending"}
        error={write.state.kind === "error" ? write.state.message : null}
        onConfirm={() => void confirm()}
        onClose={() => setOpen(false)}
      >
        <MoneyInput
          label="Cash received"
          currencyLabel="USD"
          valueCents={cents}
          onChangeCents={(next) => {
            setCents(next);
            setFieldError(undefined);
          }}
          error={fieldError}
        />
        <TextAreaField
          label="Note (optional)"
          rows={2}
          maxLength={NOTE_MAX}
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
      </AdminActionDialog>
    </>
  );
}

function CancelOrder({
  order,
  reasons,
  reasonRequired,
  open,
  setOpen,
}: {
  order: AdminOrderDetailDTO;
  reasons: CancelReason[];
  reasonRequired: boolean;
} & DialogControl) {
  const write = useAdminOrderWrite();
  const [note, setNote] = useState("");
  const [cancelReason, setCancelReason] = useState<CancelReason | "">("");
  const [errors, setErrors] = useState<{ note?: string; reason?: string }>({});

  async function confirm() {
    const next: { note?: string; reason?: string } = {};
    if (!note.trim()) next.note = "Enter a reason for cancelling.";
    else if (note.trim().length > NOTE_MAX) next.note = `Keep the reason to ${NOTE_MAX} characters or fewer.`;
    if (reasonRequired && cancelReason === "") next.reason = "Choose a cancel reason.";
    setErrors(next);
    if (next.note || next.reason) return;
    const body = { reason: note.trim(), ...(cancelReason ? { cancel_reason: cancelReason } : {}) };
    if (await write.run(() => adminOrdersApi.cancelOrder(order.id, body))) setOpen(false);
  }

  return (
    <>
      <Button
        type="button"
        variant="secondary"
        onClick={() => {
          write.reset();
          setErrors({});
          setOpen(true);
        }}
      >
        Cancel order
      </Button>
      <AdminActionDialog
        open={open}
        title="Cancel this order?"
        description={
          <p>
            Cancels every printed item not yet shipped or collected. STL files are not affected.
            {order.payment_reached_paid ? " The cancelled items will be refunded to the customer." : ""} This can&apos;t be
            undone.
          </p>
        }
        confirmLabel="Cancel order"
        destructive
        pending={write.state.kind === "pending"}
        error={write.state.kind === "error" ? write.state.message : null}
        onConfirm={() => void confirm()}
        onClose={() => setOpen(false)}
      >
        {reasons.length > 0 && (
          <SelectField
            label={reasonRequired ? "Cancel reason" : "Cancel reason (optional)"}
            value={cancelReason}
            onChange={(event) => setCancelReason(event.target.value as CancelReason | "")}
            error={errors.reason}
          >
            <option value="">Choose a reason</option>
            {reasons.map((r) => (
              <option key={r} value={r}>
                {describeCancelReason(r)}
              </option>
            ))}
          </SelectField>
        )}
        <TextAreaField
          label="Why is this order being cancelled?"
          rows={3}
          maxLength={NOTE_MAX}
          value={note}
          onChange={(event) => setNote(event.target.value)}
          error={errors.note}
        />
      </AdminActionDialog>
    </>
  );
}
