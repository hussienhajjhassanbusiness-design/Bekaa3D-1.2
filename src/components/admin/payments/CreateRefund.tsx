"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { AdminActionDialog } from "@/components/admin/orders/AdminActionDialog";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { Button } from "@/components/forms/Button";
import { MoneyInput } from "@/components/forms/MoneyInput";
import { TextAreaField } from "@/components/forms/TextAreaField";
import type { AdminOrderDetailDTO } from "@/lib/admin/orders/adminOrderTypes";
import { adminPaymentsApi } from "@/lib/admin/payments/adminPaymentsApi";
import { readAvailableBalances, REFUND_TEXT_MAX } from "@/lib/admin/payments/adminPaymentPresentation";
import type { RefundCreateDTO } from "@/lib/admin/payments/adminPaymentTypes";
import { useRefundAttemptTracker } from "@/lib/admin/payments/refundIdempotency";
import { useAdminFinancialWrite } from "@/lib/admin/payments/useAdminPayments";

// #FVS028-CREATE-REFUND (phase 5I)
//
// POST /api/v1/admin/orders/{id}/refunds: per-LINE amounts (the backend has
// no order-level or shipping amount; ADR-024: nothing was charged for
// shipping), each up to the server's own `refund_balance.lines` figure, the
// total up to `refund_balance.payment_cents`, plus a reason (1-1000). The
// limits come only from the server; this form never derives a balance from
// prices. An STL line is refunded like any other line (ADR-019: there is no
// entitlement to revoke). Refunding an unfinished printed line in full is
// refused (422 REFUND_REQUIRES_CANCELLATION): cancel it instead.
//
// Recording a refund does not move money: the administrator pays it in the
// provider's dashboard (or hands back cash) and then marks it settled.
// One Idempotency-Key per intended refund (refundIdempotency.ts).
export function CreateRefund({ order }: { order: AdminOrderDetailDTO }) {
  const router = useRouter();
  const write = useAdminFinancialWrite();
  const tracker = useRefundAttemptTracker();
  const [open, setOpen] = useState(false);
  const [amounts, setAmounts] = useState<Record<string, number | null>>({});
  const [reason, setReason] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [balances, setBalances] = useState<Record<string, number> | null>(null);

  const balance = order.refund_balance;
  if (!order.payment_reached_paid || !balance) return null;
  const serverLines = balances ?? Object.fromEntries(balance.lines.map((l) => [l.order_item_id, l.balance_cents]));
  const refundable = order.lines.filter((line) => (serverLines[line.id] ?? 0) > 0);
  if ((refundable.length === 0 || balance.payment_cents <= 0) && !open) return null;
  const currency = order.total.currency;

  async function submit() {
    const next: Record<string, string> = {};
    const items = refundable
      .map((line) => ({ order_item_id: line.id, amount_cents: amounts[line.id] ?? 0 }))
      .filter((item) => item.amount_cents > 0);
    for (const item of items) {
      if (item.amount_cents > (serverLines[item.order_item_id] ?? 0))
        next[item.order_item_id] = "More than this item's refundable balance.";
    }
    const total = items.reduce((sum, item) => sum + item.amount_cents, 0);
    if (items.length === 0) next.form = "Enter an amount for at least one item.";
    else if (total > balance!.payment_cents) next.form = "The total is more than what's left to refund on the payment.";
    if (!reason.trim()) next.reason = "Enter a reason.";
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    const body: RefundCreateDTO = {
      items: [...items].sort((a, b) => a.order_item_id.localeCompare(b.order_item_id)),
      reason: reason.trim(),
    };
    const key = tracker.keyFor(JSON.stringify({ order: order.id, ...body }));
    let failure: unknown = null;
    const created = await write.run(async () => {
      try {
        return await adminPaymentsApi.createRefund(order.id, body, key);
      } catch (error) {
        failure = error;
        throw error;
      }
    }, tracker);
    if (created) {
      setOpen(false);
      router.push(`/admin/refunds/${created.id}`);
      return;
    }
    // REFUND_EXCEEDS_AVAILABLE carries the server's current balances.
    const fresh = readAvailableBalances(failure);
    if (fresh) setBalances(fresh);
  }

  return (
    <>
      <Button
        type="button"
        variant="secondary"
        onClick={() => {
          write.reset();
          setErrors({});
          setBalances(null);
          setOpen(true);
        }}
      >
        Record a refund
      </Button>
      <AdminActionDialog
        open={open}
        title="Record a refund?"
        description={
          <p>
            Pay the refund in the provider&apos;s dashboard (or hand back the cash), then mark it settled from the
            refund page. Left to refund on the payment:{" "}
            <PriceDisplay amountCents={balance.payment_cents} currency={currency} />.
          </p>
        }
        confirmLabel="Record refund"
        pending={write.state.kind === "pending"}
        error={write.state.kind === "error" ? write.state.message : (errors.form ?? null)}
        onConfirm={() => void submit()}
        onClose={() => setOpen(false)}
      >
        {refundable.map((line) => (
          <MoneyInput
            key={line.id}
            label={`${line.name} (up to $${((serverLines[line.id] ?? 0) / 100).toFixed(2)})`}
            currencyLabel={currency}
            valueCents={amounts[line.id] ?? null}
            onChangeCents={(cents) => setAmounts((a) => ({ ...a, [line.id]: cents }))}
            error={errors[line.id]}
          />
        ))}
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
