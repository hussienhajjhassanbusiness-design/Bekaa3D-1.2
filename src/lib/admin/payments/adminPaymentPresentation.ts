import type { ApiError } from "@/lib/api/ApiError";
import { readProblemString } from "@/lib/api/problemExtensions";
import type { RefundDetailDTO } from "./adminPaymentTypes";

// #FVS028-ADMIN-PAYMENT-PRESENTATION (phase 5I)
//
// Labels reuse the order area's tables (orderStatus.describePaymentStatus,
// adminOrderPresentation.describeAdminRefundStatus/Kind and
// describePaymentProvider); this module adds the refund action offers, the
// payment history wording and the error mapping. Unknown values degrade to
// neutral text, never the raw value.

function lookup<T>(table: Readonly<Record<string, T>>, key: string): T | undefined {
  return Object.prototype.hasOwnProperty.call(table, key) ? table[key] : undefined;
}

// The backend's payment audit actions (2dfb27b).
const HISTORY_ACTION: Readonly<Record<string, string>> = {
  "payment.retry_started": "Payment retry started",
  "payment.verified": "Verified as paid",
  "payment.failed": "Marked failed",
  "payment.expired": "Marked expired",
  "payment.late_capture": "Captured after release",
  "payment.manual_confirmation": "Confirmed by hand",
  "payment.reconcile_requested": "Provider check requested",
  "payment.reconcile_deferred": "Provider check deferred",
  "payment.capture_recorded": "Capture recorded by hand",
};

export function describePaymentHistoryAction(action: string): string {
  return lookup(HISTORY_ACTION, action) ?? "Recorded action";
}

// Which refund actions to OFFER (payments/domain/refunds.py RefundAction /
// RefundRefusal; the server re-checks and refuses with 409):
//   pending -> settle, fail, void;  failed and still owed -> reissue, void;
//   settled / voided / reissued -> nothing.
export type RefundAction = "settle" | "fail" | "void" | "reissue";

export function refundActions(refund: RefundDetailDTO): RefundAction[] {
  if (refund.status === "pending") return ["settle", "fail", "void"];
  if (refund.status === "failed" && refund.owed && refund.reissued_by_refund_id === null) return ["reissue", "void"];
  return [];
}

export const REFUND_TEXT_MAX = 1000;
export const SETTLEMENT_REFERENCE_MAX = 200;

const REASONS: Readonly<Record<string, string>> = {
  not_pending: "This refund is no longer pending.",
  not_failed: "Only a failed refund can be reissued.",
  already_settled: "This refund is already settled; it can't be voided or failed.",
  already_reissued: "This refund was already reissued.",
  line_already_refunded: "One of these items is already fully refunded.",
  line_already_cancelled: "One of these items was cancelled; its refund comes from the cancellation.",
  cash_payment: "A cash payment has no provider to check or confirm.",
};

export const ADMIN_PAYMENT_MESSAGES = {
  stateChanged: "This record changed, so that action couldn't be completed. The latest state is shown.",
  orderNotPaid: "Only money that was paid can be refunded.",
  exceeds: "A refund amount is more than what's left to refund. The current balances are shown.",
  requiresCancellation: "Refunding an unfinished printed item in full needs a cancellation instead. Cancel the line from the order.",
  totalMismatch: "The order's totals don't match its lines or payment, so nothing changed. The team has been alerted.",
  keyConflict: "This refund changed while it was being recorded. Review it and submit again.",
  inProgress: "This refund is still being recorded. Wait a moment, then check before trying again.",
  manualNotAllowed: "This provider can be asked directly; use Check with provider instead.",
  referenceMismatch: "That provider reference doesn't match this payment.",
  amountMismatch: "The verified amount doesn't match the payment amount.",
  verificationUnavailable: "This payment's provider can't be asked; confirm it by hand instead.",
  notFound: "This record could not be found.",
  csrf: "Unable to verify your session. Please refresh the page and try again.",
  mfa: "Complete two-factor setup to manage payments.",
  session: "Your session has expired. Please sign in again.",
  rateLimited: "Too many requests. Please wait and try again.",
  validation: "Check the entered values and try again.",
  uncertain: "We couldn't confirm whether that went through. Check the record before trying again.",
  generic: "Something went wrong. Please try again.",
} as const;

export interface AdminPaymentErrorOutcome {
  message: string;
  // The outcome is unknown: keep the idempotency key for the resend.
  uncertain: boolean;
  // The record's own state explains the answer: re-read it.
  refetch: boolean;
}

function isApiError(value: unknown): value is ApiError {
  return typeof value === "object" && value !== null && "kind" in value && "message" in value;
}

function out(message: string, refetch = false, uncertain = false): AdminPaymentErrorOutcome {
  return { message, refetch, uncertain };
}

export function describeAdminPaymentError(error: unknown): AdminPaymentErrorOutcome {
  const M = ADMIN_PAYMENT_MESSAGES;
  if (!isApiError(error)) return out(M.generic);
  if (error.kind === "csrf") return out(M.csrf);
  if (error.kind !== "http" || error.status === undefined) return out(M.uncertain, true, true);
  switch (`${error.status} ${error.code ?? ""}`) {
    case "409 INVALID_STATE_TRANSITION": {
      const reason = readProblemString(error, "reason");
      return out((reason !== undefined ? lookup(REASONS, reason) : undefined) ?? M.stateChanged, true);
    }
    case "409 ORDER_NOT_PAID":
      return out(M.orderNotPaid, true);
    case "422 REFUND_EXCEEDS_AVAILABLE":
      return out(M.exceeds, true);
    case "422 REFUND_REQUIRES_CANCELLATION":
      return out(M.requiresCancellation, true);
    case "409 ORDER_TOTAL_MISMATCH":
      return out(M.totalMismatch, true);
    case "409 IDEMPOTENCY_KEY_CONFLICT":
      return out(M.keyConflict, true);
    case "409 IDEMPOTENCY_REQUEST_IN_PROGRESS":
      return out(M.inProgress, true, true);
    case "409 MANUAL_CONFIRMATION_NOT_ALLOWED":
      return out(M.manualNotAllowed, true);
    case "409 PAYMENT_REFERENCE_MISMATCH":
      return out(M.referenceMismatch);
    case "422 PAYMENT_AMOUNT_MISMATCH":
      return out(M.amountMismatch);
    case "503 PAYMENT_VERIFICATION_UNAVAILABLE":
      return out(M.verificationUnavailable, true);
    case "422 VALIDATION_ERROR":
      return out(M.validation);
    case "404 NOT_FOUND":
      return out(M.notFound, true);
    case "403 CSRF_INVALID":
      return out(M.csrf);
    case "401 MFA_REQUIRED":
      return out(M.mfa);
    case "401 AUTH_REQUIRED":
      return out(M.session);
    case "429 RATE_LIMITED":
      return out(M.rateLimited);
    default:
      return error.status >= 500 ? out(M.uncertain, true, true) : out(M.generic);
  }
}

// REFUND_EXCEEDS_AVAILABLE's typed `available` extension: the current
// per-line balances. Anything malformed is treated as absent.
export function readAvailableBalances(error: unknown): Record<string, number> | null {
  if (!isApiError(error) || typeof error.raw !== "object" || error.raw === null) return null;
  const available = (error.raw as Record<string, unknown>).available;
  if (typeof available !== "object" || available === null) return null;
  const lines = (available as Record<string, unknown>).lines;
  if (!Array.isArray(lines)) return null;
  const result: Record<string, number> = {};
  for (const line of lines) {
    if (typeof line !== "object" || line === null) continue;
    const { order_item_id: id, balance_cents: cents } = line as Record<string, unknown>;
    if (typeof id === "string" && typeof cents === "number" && Number.isInteger(cents)) result[id] = cents;
  }
  return result;
}
