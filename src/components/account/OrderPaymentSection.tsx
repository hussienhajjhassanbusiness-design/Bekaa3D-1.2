"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { Button } from "@/components/forms/Button";
import type { OrderDetailModel } from "@/lib/orders/orderModel";
import { describePaymentStatus } from "@/lib/orders/orderStatus";
import { formatOrderDateTime, paymentMethodLabel } from "@/lib/orders/orderFormat";
import { onlinePaymentState, type OnlinePaymentState } from "@/lib/orders/paymentVerification";
import type { RetryPaymentState } from "@/lib/orders/useRetryPayment";
import { HoldCountdown } from "./HoldCountdown";

// Live controls the page owns (usePolledOrder, useRetryPayment). Without
// them the section is read-only.
export interface OrderPaymentControls {
  polling: boolean;
  timedOut: boolean;
  onCheckAgain: () => void;
  onHoldElapsed: () => void;
  retry: {
    state: RetryPaymentState;
    onRetry: () => void;
    onResume: (url: string) => void;
  };
}

// #FVS027-PAYMENT-SECTION (phase 5F)
//
// Every sentence follows from the server's own `status`, `payment.status`,
// `hold_expires_at` and `can_retry_payment` (orderStatus.ts labels, with
// unknown values as "Status unavailable"; backend text never shown).
//   - cash: unchanged from phase 5E (amount due, never "paid" until the
//     server records a cash payment). No retry, polling, countdown or
//     redirect, whatever the flags say.
//   - online pending_payment: what the live/terminal attempt means, the
//     hold countdown, the bounded verification status with "Check
//     again", and "Retry payment" only while can_retry_payment is true.
//   - paid / refunded / partially refunded: what the server says; refund
//     rows are listed by the page's Refunds section. No refund action.
export function OrderPaymentSection({ order, controls }: { order: OrderDetailModel; controls?: OrderPaymentControls }) {
  const cash = order.paymentMethod === "cash";
  const descriptor = order.payment ? describePaymentStatus(order.payment.status) : null;

  return (
    <section aria-label="Payment" className="flex flex-col gap-3 rounded-md border border-border-default bg-white p-4">
      <h2 className="text-h3 font-bold text-text-primary">Payment</h2>
      <dl className="flex flex-col gap-2 text-body text-text-primary">
        <div className="flex justify-between gap-2">
          <dt className="text-text-secondary">Method</dt>
          <dd>{paymentMethodLabel(order.paymentMethod)}</dd>
        </div>
        {descriptor && (
          <div className="flex items-center justify-between gap-2">
            <dt className="text-text-secondary">Payment status</dt>
            <dd>
              <StatusBadge label={descriptor.label} tone={descriptor.tone} />
            </dd>
          </div>
        )}
      </dl>
      {cash ? <CashPayment order={order} /> : <OnlinePayment order={order} controls={controls} />}
    </section>
  );
}

function CashPayment({ order }: { order: OrderDetailModel }) {
  const where =
    order.fulfillmentMethod === "pickup" ? "when you pick up your order" : "to the courier on delivery";
  if (!order.paymentDue || !order.amountDue) return null;
  return (
    <p className="rounded-md border-l-4 border-l-info bg-info-bg p-3 text-body text-text-primary">
      Payment due in cash {where}:{" "}
      <span className="font-semibold">
        <PriceDisplay amountCents={order.amountDue.amountCents} currency={order.amountDue.currency} />
      </span>
      . This order hasn&apos;t been paid yet.
    </p>
  );
}

const UNPAID_COPY: Readonly<Partial<Record<OnlinePaymentState, string>>> = {
  awaiting:
    "This order hasn't been confirmed as paid. We only mark an order paid once our payment provider confirms it to us.",
  processing:
    "Your payment is being processed. This order hasn't been confirmed as paid yet; it updates as soon as our payment provider confirms it.",
  failed: "Your last payment attempt didn't go through. This order hasn't been paid.",
  expired: "Your last payment attempt expired before it was completed. This order hasn't been paid.",
};

const UNPAID_FALLBACK =
  "This order hasn't been confirmed as paid. We only mark an order paid once our payment provider confirms it to us.";

const SETTLED_COPY: Readonly<Partial<Record<OnlinePaymentState, string>>> = {
  paid: "Your payment has been confirmed.",
  refunded: "This payment has been refunded.",
  "partially-refunded": "Part of this payment has been refunded.",
  failed: "This payment didn't go through.",
  expired: "This payment expired before it was completed.",
};

function OnlinePayment({ order, controls }: { order: OrderDetailModel; controls?: OrderPaymentControls }) {
  const state = onlinePaymentState(order.payment?.status);
  const unpaid = order.status === "pending_payment" && order.cancelledAt === null;
  const retry = controls?.retry;
  const showRetry = Boolean(retry) && (order.canRetryPayment || (retry && retry.state.kind !== "idle"));

  if (!unpaid) {
    const copy = SETTLED_COPY[state];
    return (
      <>
        {copy && <p className="text-body text-text-primary">{copy}</p>}
        {!order.payment && <p className="text-body text-text-secondary">No payment has been recorded for this order.</p>}
        {retry && retry.state.kind !== "idle" && <RetryOutcome state={retry.state} onResume={retry.onResume} orderId={order.id} />}
      </>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2 rounded-md border-l-4 border-l-warning bg-warning-bg p-3 text-body text-text-primary">
        <p>{UNPAID_COPY[state] ?? UNPAID_FALLBACK}</p>
        {order.holdExpiresAt && (
          <>
            <p>If it&apos;s still unpaid, this order may be released after {formatOrderDateTime(order.holdExpiresAt)}.</p>
            {controls && (
              <HoldCountdown key={order.holdExpiresAt} expiresAt={order.holdExpiresAt} onElapsed={controls.onHoldElapsed} />
            )}
          </>
        )}
      </div>

      {controls && (controls.polling || controls.timedOut) && (
        <div role="status" className="flex flex-col items-start gap-2 text-body text-text-secondary">
          {controls.polling ? (
            <p>Checking for a payment update…</p>
          ) : (
            <>
              <p>
                We haven&apos;t received a confirmation from our payment provider yet. It can take a few minutes; this
                order shows the latest status we have.
              </p>
              <Button type="button" variant="secondary" onClick={controls.onCheckAgain}>
                Check again
              </Button>
            </>
          )}
        </div>
      )}

      {retry && showRetry && (
        <div className="flex flex-col items-start gap-2">
          {order.canRetryPayment && <RetryButton state={retry.state} onRetry={retry.onRetry} />}
          <RetryOutcome state={retry.state} onResume={retry.onResume} orderId={order.id} />
        </div>
      )}
    </div>
  );
}

function RetryButton({ state, onRetry }: { state: RetryPaymentState; onRetry: () => void }) {
  const busy = state.kind === "sending" || state.kind === "redirecting";
  const uncertain = state.kind === "error" && state.outcome.uncertain;
  const label =
    state.kind === "sending"
      ? "Starting payment…"
      : state.kind === "redirecting"
        ? "Opening payment page…"
        : uncertain
          ? "Try again"
          : "Retry payment";
  return (
    <Button type="button" onClick={onRetry} isLoading={busy}>
      {label}
    </Button>
  );
}

function RetryOutcome({
  state,
  onResume,
  orderId,
}: {
  state: RetryPaymentState;
  onResume: (url: string) => void;
  orderId: string;
}): ReactNode {
  if (state.kind === "started") {
    return (
      <p role="status" className="text-body text-text-primary">
        Your new payment was started. This order updates once our payment provider confirms it.
      </p>
    );
  }
  if (state.kind !== "error") return null;
  const { outcome } = state;
  const resumeUrl = outcome.resumeUrl;
  return (
    <div role="alert" className="flex flex-col items-start gap-2 rounded-md border-l-4 border-l-danger bg-danger-bg p-3">
      <p className="text-body text-text-primary">{outcome.message}</p>
      {resumeUrl && (
        <Button type="button" variant="secondary" onClick={() => onResume(resumeUrl)}>
          Continue to payment
        </Button>
      )}
      {outcome.kind === "session-expired" && (
        <Link
          href={`/login?returnTo=${encodeURIComponent(`/account/orders/${orderId}`)}`}
          className="font-semibold text-brand-dark-green underline"
        >
          Sign in
        </Link>
      )}
      {outcome.kind === "verify-email" && (
        <Link href="/verify-email/resend" className="font-semibold text-brand-dark-green underline">
          Resend verification email
        </Link>
      )}
    </div>
  );
}
