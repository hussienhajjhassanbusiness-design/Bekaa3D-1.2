"use client";

import { useState } from "react";
import { AdminActionDialog } from "@/components/admin/orders/AdminActionDialog";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { Alert } from "@/components/feedback/Alert";
import { Button } from "@/components/forms/Button";
import { MoneyInput } from "@/components/forms/MoneyInput";
import { SelectField } from "@/components/forms/SelectField";
import { TextAreaField } from "@/components/forms/TextAreaField";
import { TextField } from "@/components/forms/TextField";
import type { AdminOrderDetailDTO } from "@/lib/admin/orders/adminOrderTypes";
import { adminPaymentsApi } from "@/lib/admin/payments/adminPaymentsApi";
import {
  readAvailableBalances,
  readChargeableCents,
  REFUND_TEXT_MAX,
} from "@/lib/admin/payments/adminPaymentPresentation";
import type { ChargebackCreateDTO } from "@/lib/admin/payments/adminPaymentTypes";
import { useRefundAttemptTracker } from "@/lib/admin/payments/refundIdempotency";
import { useAdminFinancialWrite } from "@/lib/admin/payments/useAdminPayments";

const DISPUTE_REFERENCE_MAX = 200;

// #FVS-CHARGEBACK-CREATE (phase 6A)
//
// POST /api/v1/admin/orders/{id}/chargebacks + Idempotency-Key (create only;
// the backend has no update / resolve / acknowledge route, so a recorded
// chargeback stays read-only). Online payments only (a cash payment is 422
// CHARGEBACK_NOT_ONLINE, so cash attempts are not listed). The bank's charge
// first voids and absorbs the payment's open refunds; any item amounts
// allocate the rest and must total the server's `chargeable_cents`. The
// frontend computes none of that: the first answer to a wrong allocation
// (422 CHARGEBACK_ALLOCATION_INVALID) carries `chargeable_cents` and the line
// balances, which the form then shows. One key per intended chargeback.
export function CreateChargeback({ order }: { order: AdminOrderDetailDTO }) {
  const write = useAdminFinancialWrite();
  const tracker = useRefundAttemptTracker();
  const online = order.payments.filter(
    (p) => p.provider !== "cash" && ["paid", "partially_refunded", "refunded"].includes(p.status)
  );
  const [open, setOpen] = useState(false);
  const [paymentId, setPaymentId] = useState(online[0]?.id ?? "");
  const [reference, setReference] = useState("");
  const [charged, setCharged] = useState<number | null>(null);
  const [receivedAt, setReceivedAt] = useState("");
  const [reason, setReason] = useState("");
  const [amounts, setAmounts] = useState<Record<string, number | null>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [server, setServer] = useState<{ chargeable: number | null; balances: Record<string, number> | null } | null>(
    null
  );
  const [recorded, setRecorded] = useState(false);

  if (online.length === 0 && !open) return null;
  const currency = order.total.currency;

  async function submit() {
    const next: Record<string, string> = {};
    if (!paymentId) next.payment = "Choose the charged payment.";
    if (!reference.trim()) next.reference = "Enter the provider's dispute reference.";
    if (charged === null || charged <= 0) next.charged = "Enter the amount the bank charged back.";
    if (!receivedAt || Number.isNaN(Date.parse(receivedAt))) next.received = "Enter when the chargeback was received.";
    if (!reason.trim()) next.reason = "Enter a reason.";
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    const items = order.lines
      .map((line) => ({ order_item_id: line.id, amount_cents: amounts[line.id] ?? 0 }))
      .filter((item) => item.amount_cents > 0)
      .sort((a, b) => a.order_item_id.localeCompare(b.order_item_id));
    const body: ChargebackCreateDTO = {
      payment_id: paymentId,
      provider_dispute_reference: reference.trim(),
      charged_cents: charged ?? 0,
      items,
      reason: reason.trim(),
      // datetime-local is the admin's local time; sent as an aware instant.
      received_at: new Date(receivedAt).toISOString(),
    };
    const key = tracker.keyFor(JSON.stringify({ order: order.id, ...body }));
    let failure: unknown = null;
    const created = await write.run(async () => {
      try {
        return await adminPaymentsApi.createChargeback(order.id, body, key);
      } catch (error) {
        failure = error;
        throw error;
      }
    }, tracker);
    if (created) {
      setOpen(false);
      setRecorded(true);
      return;
    }
    const chargeable = readChargeableCents(failure);
    const balances = readAvailableBalances(failure);
    if (chargeable !== null || balances) setServer({ chargeable, balances });
  }

  return (
    <>
      {recorded && (
        <Alert variant="success" message="Chargeback recorded. The order's refunds and balances are updated below." />
      )}
      {online.length > 0 && (
        <Button
          type="button"
          variant="secondary"
          onClick={() => {
            write.reset();
            setErrors({});
            setServer(null);
            setRecorded(false);
            setOpen(true);
          }}
        >
          Record a chargeback
        </Button>
      )}
      <AdminActionDialog
        open={open}
        title="Record a chargeback?"
        description={
          <p>
            Record a dispute the bank already charged back. It voids this payment&apos;s open refunds and absorbs them.
            A recorded chargeback can&apos;t be edited.
          </p>
        }
        confirmLabel="Record chargeback"
        destructive
        pending={write.state.kind === "pending"}
        error={write.state.kind === "error" ? write.state.message : null}
        onConfirm={() => void submit()}
        onClose={() => setOpen(false)}
      >
        {online.length > 1 && (
          <SelectField
            label="Payment"
            value={paymentId}
            onChange={(e) => setPaymentId(e.target.value)}
            error={errors.payment}
          >
            {online.map((p) => (
              <option key={p.id} value={p.id}>
                {`${(p.amount.amount_cents / 100).toFixed(2)} ${p.amount.currency} · ${new Date(p.initiated_at).toLocaleDateString("en-GB")}`}
              </option>
            ))}
          </SelectField>
        )}
        <TextField
          label="Provider dispute reference"
          maxLength={DISPUTE_REFERENCE_MAX}
          value={reference}
          onChange={(e) => setReference(e.target.value)}
          error={errors.reference}
        />
        <MoneyInput
          label="Amount charged back"
          currencyLabel={currency}
          valueCents={charged}
          onChangeCents={setCharged}
          error={errors.charged}
        />
        <TextField
          label="Received at"
          type="datetime-local"
          value={receivedAt}
          onChange={(e) => setReceivedAt(e.target.value)}
          error={errors.received}
        />
        {server?.chargeable !== null && server?.chargeable !== undefined && (
          <p className="text-body-md text-on-surface">
            Items must total <PriceDisplay amountCents={server.chargeable} currency={currency} /> (the charge left after
            the open refunds).
          </p>
        )}
        <fieldset className="flex flex-col gap-2">
          <legend className="font-label text-label-sm uppercase text-on-surface">Items covered (optional)</legend>
          {order.lines.map((line) => (
            <MoneyInput
              key={line.id}
              label={
                server?.balances && server.balances[line.id] !== undefined
                  ? `${line.name} (up to $${(server.balances[line.id]! / 100).toFixed(2)})`
                  : line.name
              }
              currencyLabel={currency}
              valueCents={amounts[line.id] ?? null}
              onChangeCents={(cents) => setAmounts((a) => ({ ...a, [line.id]: cents }))}
            />
          ))}
        </fieldset>
        <TextAreaField
          label="Reason"
          rows={3}
          maxLength={REFUND_TEXT_MAX}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          error={errors.reason}
        />
      </AdminActionDialog>
    </>
  );
}
