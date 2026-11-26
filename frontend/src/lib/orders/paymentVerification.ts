import type { OrderDetailReadDTO } from "./orderTypes";

// #FVS027-PAYMENT-VERIFICATION (phase 5F)
//
// The customer's payment truth is GET /api/v1/me/orders/{id} (`status`,
// `payment`, `can_retry_payment`, `hold_expires_at`): there is no customer
// payment route (backend 2dfb27b; docs/payment-recovery.md). Everything
// here is a pure reading of that response.
//
// Transient = the backend's own "live attempt" set
// (ordering/domain/customer_view.py LIVE_ATTEMPT_STATUSES = pending,
// processing) on an online order still `pending_payment` and not
// cancelled. Only then can the provider's answer (webhook -> background
// verification, or the 15-minute reconcile job) still change the order,
// so only then is the detail re-read. Never for cash, never with no
// payment row, never once the order or the payment is terminal.
export const LIVE_PAYMENT_STATUSES: readonly string[] = ["pending", "processing"];

export function isPaymentTransient(order: OrderDetailReadDTO | undefined | null): boolean {
  if (!order) return false;
  return (
    order.payment_method === "online" &&
    order.status === "pending_payment" &&
    order.cancelled_at === null &&
    order.payment !== null &&
    LIVE_PAYMENT_STATUSES.includes(order.payment.status)
  );
}

// Bounded re-reading. The mock provider's webhook is verified in a
// background task right after it lands, so a completed payment shows
// within seconds; a real provider can be slower, and the reconcile job
// runs every 15 minutes, so the page does not chase it: after the bound
// it stops and offers "Check again" (a new bounded window).
export const PAYMENT_POLLING = {
  fastIntervalMs: 3_000,
  fastPhaseMs: 30_000,
  slowIntervalMs: 10_000,
  maxDurationMs: 180_000,
} as const;

// How an online order's payment reads to the customer. Every value is the
// server's; `unknown` covers any status this frontend does not know.
export type OnlinePaymentState =
  | "none"
  | "awaiting"
  | "processing"
  | "paid"
  | "failed"
  | "expired"
  | "refunded"
  | "partially-refunded"
  | "unknown";

const STATE_BY_STATUS: Readonly<Record<string, OnlinePaymentState>> = {
  pending: "awaiting",
  processing: "processing",
  paid: "paid",
  failed: "failed",
  expired: "expired",
  refunded: "refunded",
  partially_refunded: "partially-refunded",
};

export function onlinePaymentState(paymentStatus: string | null | undefined): OnlinePaymentState {
  if (paymentStatus === null || paymentStatus === undefined) return "none";
  return Object.prototype.hasOwnProperty.call(STATE_BY_STATUS, paymentStatus)
    ? STATE_BY_STATUS[paymentStatus]!
    : "unknown";
}
