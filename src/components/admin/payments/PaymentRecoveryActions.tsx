"use client";

import Link from "next/link";
import { useState } from "react";
import { AdminActionDialog } from "@/components/admin/orders/AdminActionDialog";
import { Alert } from "@/components/feedback/Alert";
import { Button } from "@/components/forms/Button";
import { MoneyInput } from "@/components/forms/MoneyInput";
import { TextAreaField } from "@/components/forms/TextAreaField";
import { TextField } from "@/components/forms/TextField";
import { adminPaymentsApi } from "@/lib/admin/payments/adminPaymentsApi";
import { REFUND_TEXT_MAX } from "@/lib/admin/payments/adminPaymentPresentation";
import type { AdminPaymentDetailDTO } from "@/lib/admin/payments/adminPaymentTypes";
import { useRefundAttemptTracker } from "@/lib/admin/payments/refundIdempotency";
import { useAdminFinancialWrite } from "@/lib/admin/payments/useAdminPayments";

const REASON_MIN = 10;
const PAID_LIKE = new Set(["paid", "partially_refunded", "refunded"]);

// #FVS-PAYMENT-RECOVERY-ACTIONS (phase 6A)
//
// Two payment-recovery writes, each offered only on the server's own gate:
//   - Release order (POST /admin/orders/{id}/release): exactly while the
//     payment detail lists `release_order` (unpaid online order, hold + 24 h
//     grace elapsed). Reason 10-1000. When the payment has unprocessed
//     provider events the administrator must tick "reviewed" (the server
//     refuses otherwise). Success cancels the order server-side; nothing is
//     changed locally, the order and payment are re-read.
//   - Record late capture (POST /admin/payments/{id}/record-capture +
//     Idempotency-Key): for a provider without a status API (the server
//     offers `confirm`, never with the mock), an attempt that never reached
//     paid and has no late capture yet. The amount and reference are what
//     the provider's dashboard shows, typed by the administrator; the server
//     creates a late-capture refund obligation.
export function PaymentRecoveryActions({ detail }: { detail: AdminPaymentDetailDTO }) {
  const canRelease = detail.available_actions.includes("release_order");
  const canCapture =
    detail.available_actions.includes("confirm") && !PAID_LIKE.has(detail.payment.status) && detail.payment.late_captured_at === null;
  const [open, setOpen] = useState<"release" | "capture" | null>(null);
  if (!canRelease && !canCapture && open === null) return null;

  return (
    <>
      {(canRelease || open === "release") && <ReleaseOrder detail={detail} open={open === "release"} setOpen={(v) => setOpen(v ? "release" : null)} />}
      {(canCapture || open === "capture") && <RecordCapture detail={detail} open={open === "capture"} setOpen={(v) => setOpen(v ? "capture" : null)} />}
    </>
  );
}

interface Control {
  detail: AdminPaymentDetailDTO;
  open: boolean;
  setOpen: (open: boolean) => void;
}

function ReleaseOrder({ detail, open, setOpen }: Control) {
  const write = useAdminFinancialWrite();
  const [reason, setReason] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [errors, setErrors] = useState<{ reason?: string; reviewed?: string }>({});
  const [released, setReleased] = useState(false);
  const pendingEvents = detail.payment.unprocessed_event_count;

  async function confirm() {
    const next: typeof errors = {};
    if (reason.trim().length < REASON_MIN) next.reason = `Explain in at least ${REASON_MIN} characters.`;
    if (pendingEvents > 0 && !reviewed) next.reviewed = "Confirm you reviewed the provider events.";
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    const body = { reason: reason.trim(), events_reviewed: pendingEvents > 0 ? reviewed : false };
    if (await write.run(() => adminPaymentsApi.releaseOrder(detail.order.id, body))) {
      setOpen(false);
      setReleased(true);
    }
  }

  return (
    <>
      {released && <Alert variant="success" message="The order was released. Its current state is shown below." />}
      <Button
        type="button"
        variant="secondary"
        onClick={() => {
          write.reset();
          setErrors({});
          setOpen(true);
        }}
      >
        Release order
      </Button>
      <AdminActionDialog
        open={open}
        title="Release this unpaid order?"
        description={
          <p>
            Cancels order {detail.order.order_number}, which was never paid, and frees its stock. The provider is not contacted. This
            can&apos;t be undone.
          </p>
        }
        confirmLabel="Release order"
        destructive
        pending={write.state.kind === "pending"}
        error={write.state.kind === "error" ? write.state.message : null}
        onConfirm={() => void confirm()}
        onClose={() => setOpen(false)}
      >
        <TextAreaField
          label="Reason"
          rows={3}
          maxLength={REFUND_TEXT_MAX}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          error={errors.reason}
        />
        {pendingEvents > 0 && (
          <div>
            <label className="flex items-start gap-2 text-body text-text-primary">
              <input type="checkbox" checked={reviewed} onChange={(e) => setReviewed(e.target.checked)} className="mt-1" />
              <span>
                I reviewed the {pendingEvents} unprocessed provider event{pendingEvents === 1 ? "" : "s"} for this payment.
              </span>
            </label>
            {errors.reviewed && <p className="mt-1 text-caption text-danger">{errors.reviewed}</p>}
          </div>
        )}
      </AdminActionDialog>
    </>
  );
}

function RecordCapture({ detail, open, setOpen }: Control) {
  const write = useAdminFinancialWrite();
  const tracker = useRefundAttemptTracker();
  const [cents, setCents] = useState<number | null>(null);
  const [reference, setReference] = useState("");
  const [reason, setReason] = useState("");
  const [errors, setErrors] = useState<{ amount?: string; reference?: string; reason?: string }>({});
  const [refundId, setRefundId] = useState<string | null>(null);

  async function confirm() {
    const next: typeof errors = {};
    if (cents === null || cents <= 0) next.amount = "Enter the amount the dashboard shows captured.";
    if (!reference.trim()) next.reference = "Enter the dashboard reference.";
    if (reason.trim().length < REASON_MIN) next.reason = `Explain in at least ${REASON_MIN} characters.`;
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    const body = {
      captured_amount_cents: cents ?? 0,
      captured_currency: detail.payment.currency,
      dashboard_reference: reference.trim(),
      reason: reason.trim(),
    };
    const key = tracker.keyFor(JSON.stringify({ payment: detail.payment.id, ...body }));
    const read = await write.run(() => adminPaymentsApi.recordCapture(detail.payment.id, body, key), tracker);
    if (read) {
      setOpen(false);
      setRefundId(read.refund_id);
    }
  }

  return (
    <>
      {refundId && (
        <p className="text-body text-text-primary">
          Late capture recorded.{" "}
          <Link href={`/admin/refunds/${refundId}`} className="text-text-link underline">
            Open its refund obligation
          </Link>
        </p>
      )}
      <Button
        type="button"
        variant="secondary"
        onClick={() => {
          write.reset();
          setErrors({});
          setOpen(true);
        }}
      >
        Record late capture
      </Button>
      <AdminActionDialog
        open={open}
        title="Record a late capture?"
        description={
          <p>
            Use only when the provider&apos;s dashboard shows money captured for this attempt with a different amount. A refund
            obligation is created for you to pay back and settle.
          </p>
        }
        confirmLabel="Record late capture"
        pending={write.state.kind === "pending"}
        error={write.state.kind === "error" ? write.state.message : null}
        onConfirm={() => void confirm()}
        onClose={() => setOpen(false)}
      >
        <MoneyInput label="Captured amount" currencyLabel={detail.payment.currency} valueCents={cents} onChangeCents={setCents} error={errors.amount} />
        <TextField label="Dashboard reference" maxLength={255} value={reference} onChange={(e) => setReference(e.target.value)} error={errors.reference} />
        <TextAreaField label="Reason" rows={3} maxLength={REFUND_TEXT_MAX} value={reason} onChange={(e) => setReason(e.target.value)} error={errors.reason} />
      </AdminActionDialog>
    </>
  );
}
