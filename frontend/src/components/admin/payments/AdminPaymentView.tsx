"use client";

import { AdminBackLink, AdminRow, AdminSection as Section } from "@/components/admin/adminUi";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import { AdminActionDialog } from "@/components/admin/orders/AdminActionDialog";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { Alert } from "@/components/feedback/Alert";
import { Button } from "@/components/forms/Button";
import { MoneyInput } from "@/components/forms/MoneyInput";
import { TextAreaField } from "@/components/forms/TextAreaField";
import { TextField } from "@/components/forms/TextField";
import { describePaymentProvider } from "@/lib/admin/orders/adminOrderPresentation";
import { adminPaymentsApi } from "@/lib/admin/payments/adminPaymentsApi";
import { describePaymentHistoryAction, REFUND_TEXT_MAX } from "@/lib/admin/payments/adminPaymentPresentation";
import type { AdminPaymentDetailDTO } from "@/lib/admin/payments/adminPaymentTypes";
import { useAdminFinancialWrite } from "@/lib/admin/payments/useAdminPayments";
import { PaymentRecoveryActions } from "./PaymentRecoveryActions";
import { formatOrderDateTime } from "@/lib/orders/orderFormat";
import { describeOrderStatus, describePaymentStatus } from "@/lib/orders/orderStatus";

// #FVS028-ADMIN-PAYMENT-VIEW (phase 5I)
//
// GET /api/v1/admin/payments/{id}: the payment, its order, its webhook
// events (no payloads; the backend's processing_error text is never shown,
// only that processing failed) and its audit history (no `data`). Actions
// are exactly the server's `available_actions`:
//   reconcile -> POST …/reconcile (202: the check runs after the answer);
//   confirm   -> POST …/confirm, only for a provider without a status API.
//   release_order / late capture -> PaymentRecoveryActions (phase 6A).
// Nothing is marked paid locally.
export function AdminPaymentView({ detail }: { detail: AdminPaymentDetailDTO }) {
  const { payment, order } = detail;
  const status = describePaymentStatus(payment.status);
  const orderStatus = describeOrderStatus(order.status);

  return (
    <article aria-labelledby="payment-heading" className="flex min-w-0 flex-col gap-6 break-words">
      <header className="flex flex-col gap-2">
        <div>
          <AdminBackLink href="/admin/payments">Back to payments</AdminBackLink>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <h1 id="payment-heading" className="break-words font-headline text-headline-lg text-on-surface">
            Payment for order {order.order_number}
          </h1>
          <StatusBadge label={status.label} tone={status.tone} />
        </div>
      </header>

      <PaymentActions detail={detail} />

      <div className="grid gap-6 desktop:grid-cols-2">
        <Section title="Payment">
          <dl className="flex flex-col gap-2 text-body-md">
            <Row label="Provider">{describePaymentProvider(payment.provider)}</Row>
            <Row label="Amount">
              <PriceDisplay amountCents={payment.amount_cents} currency={payment.currency} />
            </Row>
            {payment.captured_amount_cents !== null && payment.captured_currency && (
              <Row label="Captured">
                <PriceDisplay amountCents={payment.captured_amount_cents} currency={payment.captured_currency} />
              </Row>
            )}
            {payment.provider_payment_id && <Row label="Provider reference">{payment.provider_payment_id}</Row>}
            <Row label="Started">{formatOrderDateTime(payment.initiated_at)}</Row>
            {payment.verified_at && <Row label="Verified">{formatOrderDateTime(payment.verified_at)}</Row>}
            {payment.failed_at && <Row label="Failed">{formatOrderDateTime(payment.failed_at)}</Row>}
            {payment.expired_at && <Row label="Expired">{formatOrderDateTime(payment.expired_at)}</Row>}
            {payment.late_captured_at && (
              <Row label="Captured late">{formatOrderDateTime(payment.late_captured_at)}</Row>
            )}
            {payment.unprocessed_event_count > 0 && (
              <Row label="Unprocessed events">{payment.unprocessed_event_count}</Row>
            )}
          </dl>
        </Section>
        <Section title="Order">
          <dl className="flex flex-col gap-2 text-body-md">
            <Row label="Order">
              <Link
                href={`/admin/orders/${order.id}`}
                className="font-semibold text-primary underline underline-offset-2 hover:text-primary-container"
              >
                {order.order_number}
              </Link>
            </Row>
            <Row label="Status">
              <StatusBadge label={orderStatus.label} tone={orderStatus.tone} />
            </Row>
            <Row label="Total">
              <PriceDisplay amountCents={order.total_cents} currency={order.currency} />
            </Row>
            <Row label="Placed">{formatOrderDateTime(order.placed_at)}</Row>
            {order.hold_expires_at && <Row label="Hold ends">{formatOrderDateTime(order.hold_expires_at)}</Row>}
          </dl>
        </Section>
      </div>

      <Section title="Provider events">
        {detail.events.length === 0 ? (
          <p className="text-xs text-on-surface-variant">No provider events received.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {detail.events.map((e) => (
              <li key={e.id} className="text-body-md text-on-surface">
                {e.event_type ?? "Event"} · received {formatOrderDateTime(e.received_at)}
                <span className="block text-xs text-on-surface-variant">
                  {e.signature_valid === false ? "Invalid signature · " : ""}
                  {e.processing_error
                    ? "Processing failed"
                    : e.processed_at
                      ? `Processed ${formatOrderDateTime(e.processed_at)}`
                      : "Not processed yet"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="History">
        {detail.history.length === 0 ? (
          <p className="text-xs text-on-surface-variant">No recorded actions.</p>
        ) : (
          <ol className="flex flex-col gap-2">
            {detail.history.map((h, i) => (
              <li key={`${h.created_at}-${i}`} className="text-body-md text-on-surface">
                {describePaymentHistoryAction(h.action)}
                <span className="block text-xs text-on-surface-variant">
                  {formatOrderDateTime(h.created_at)} · {h.actor_user_id ? "Staff" : "System"}
                </span>
              </li>
            ))}
          </ol>
        )}
      </Section>
    </article>
  );
}

function PaymentActions({ detail }: { detail: AdminPaymentDetailDTO }) {
  const write = useAdminFinancialWrite();
  const [open, setOpen] = useState<"reconcile" | "confirm" | null>(null);
  const [queued, setQueued] = useState(false);
  const [reference, setReference] = useState("");
  const [cents, setCents] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [errors, setErrors] = useState<{ reference?: string; amount?: string; reason?: string }>({});
  const actions = detail.available_actions.filter((a) => a === "reconcile" || a === "confirm");
  const recovery =
    detail.available_actions.includes("release_order") ||
    (detail.available_actions.includes("confirm") && detail.payment.late_captured_at === null);
  if (actions.length === 0 && open === null && !recovery) return null;

  async function reconcile() {
    if (await write.run(() => adminPaymentsApi.reconcilePayment(detail.payment.id))) {
      setOpen(null);
      setQueued(true);
    }
  }

  async function confirm() {
    const next: typeof errors = {};
    if (!reference.trim()) next.reference = "Enter the provider's reference.";
    if (cents === null || cents < 0) next.amount = "Enter the amount the provider shows.";
    if (reason.trim().length < 10) next.reason = "Explain in at least 10 characters.";
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    const body = {
      provider_reference: reference.trim(),
      verified_amount_cents: cents ?? 0,
      verified_currency: detail.payment.currency,
      reason: reason.trim(),
    };
    if (await write.run(() => adminPaymentsApi.confirmPayment(detail.payment.id, body))) setOpen(null);
  }

  const error = write.state.kind === "error" ? write.state.message : null;
  return (
    <section
      aria-label="Payment actions"
      className="flex flex-col gap-3 rounded-card border border-error/30 border-t-4 border-t-error bg-surface-container-lowest p-5 shadow-sm tablet:p-6"
    >
      <h2 className="font-headline text-headline-md text-on-surface">Payment actions</h2>
      {queued && (
        <Alert
          variant="info"
          message="Check requested. The result appears here once the provider answers; refresh in a moment."
        />
      )}
      <div className="flex flex-wrap gap-2">
        {actions.includes("reconcile") && (
          <Button
            type="button"
            onClick={() => {
              write.reset();
              setOpen("reconcile");
            }}
          >
            Check with provider
          </Button>
        )}
        <PaymentRecoveryActions detail={detail} />
        {actions.includes("confirm") && (
          <Button
            type="button"
            onClick={() => {
              write.reset();
              setErrors({});
              setOpen("confirm");
            }}
          >
            Confirm by hand
          </Button>
        )}
      </div>
      <AdminActionDialog
        open={open === "reconcile"}
        title="Check this payment with the provider?"
        description={
          <p>Asks the provider for this payment&apos;s status. The result is applied by the server when it answers.</p>
        }
        confirmLabel="Check with provider"
        pending={write.state.kind === "pending"}
        error={error}
        onConfirm={() => void reconcile()}
        onClose={() => setOpen(null)}
      />
      <AdminActionDialog
        open={open === "confirm"}
        title="Confirm this payment by hand?"
        description={
          <p>Only after checking the provider&apos;s dashboard. The amount must match the payment exactly.</p>
        }
        confirmLabel="Confirm payment"
        pending={write.state.kind === "pending"}
        error={error}
        onConfirm={() => void confirm()}
        onClose={() => setOpen(null)}
      >
        <TextField
          label="Provider reference"
          value={reference}
          maxLength={255}
          onChange={(e) => setReference(e.target.value)}
          error={errors.reference}
        />
        <MoneyInput
          label="Amount the provider shows"
          currencyLabel={detail.payment.currency}
          valueCents={cents}
          onChangeCents={setCents}
          error={errors.amount}
        />
        <TextAreaField
          label="Reason"
          rows={3}
          maxLength={REFUND_TEXT_MAX}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          error={errors.reason}
        />
      </AdminActionDialog>
    </section>
  );
}

// Provider references and ids are long opaque strings: break anywhere.
function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <AdminRow label={label} breakAll>
      {children}
    </AdminRow>
  );
}
