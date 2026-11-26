import type { ApiError } from "@/lib/api/ApiError";
import { readProblemString } from "@/lib/api/problemExtensions";
import { isFollowableRedirect } from "@/lib/checkout/checkoutModel";

// #FVS027-PAYMENT-RETRY-ERRORS (phase 5F)
//
// Classifies every POST /api/v1/me/orders/{order_id}/payments failure on
// status + Problem.code + typed extensions only (backend 2dfb27b
// ordering/api/payment_retry.py `_RESPONSES` / `_translate`;
// docs/payment-recovery.md). Problem.title/detail are never returned.
//
// There is no `PAYMENT_NOT_RETRYABLE` code: a refused retry is
// 409 INVALID_STATE_TRANSITION with `reason` cash_order | order_cancelled |
// order_not_payable | checkout_hold_expired | offer_checkout_expired.
//
//   uncertain    - the server may or may not have started an attempt
//                  (network, timeout, unparseable body, a 5xx other than
//                  the 502, IDEMPOTENCY_REQUEST_IN_PROGRESS). The caller
//                  keeps the key, so the customer's resend replays the
//                  real outcome instead of starting a second attempt.
//   refetchOrder - the order's own state explains the answer; re-read the
//                  canonical order detail.
//   resumeUrl    - 409 PAYMENT_ALREADY_ACTIVE for a `pending` attempt
//                  carries that attempt's `redirect_url` (null while
//                  `processing`). Offered only if absolute http(s).

export const PAYMENT_RETRY_MESSAGES = {
  generic: "Something went wrong starting your payment. Nothing has been charged. Please try again.",
  uncertain:
    "We couldn't confirm whether your payment was started. Try again: it's safe, and it won't start a second payment.",
  inProgress: "Your payment is still being started. Wait a moment, then try again.",
  alreadyActiveResume: "A payment for this order is already in progress. You can continue it.",
  alreadyActiveProcessing:
    "A payment for this order is already being processed. Its result will show here once our payment provider confirms it.",
  cashOrder: "This order is paid in cash, so it can't be paid online.",
  orderCancelled: "This order was cancelled, so it can no longer be paid.",
  notPayable: "This order can no longer be paid online.",
  holdExpired: "The time to pay for this order has ended, so it can no longer be paid online.",
  offerExpired: "The checkout window for your accepted offer has ended, so this order can no longer be paid.",
  providerUnavailable: "Your payment couldn't be started, so nothing has been charged. Please try again.",
  keyConflict: "Something changed while your payment was being started. Please try again.",
  onlineUnavailable: "Online payment isn't available right now. Please try again later.",
  methodNotAllowed: "This payment method can't be used for this order.",
  csrf: "Unable to verify your session. Please refresh the page and try again.",
  verifyEmail: "Verify your email address before paying for this order.",
  sessionExpired: "Your session has expired. Please sign in again to pay for this order.",
  notFound: "We couldn't find this order in your account.",
  rateLimited: "Too many payment attempts. Please wait a while and try again.",
} as const;

export type PaymentRetryErrorKind =
  | "uncertain"
  | "already-active"
  | "not-retryable"
  | "provider-unavailable"
  | "verify-email"
  | "session-expired"
  | "message";

export interface PaymentRetryErrorOutcome {
  kind: PaymentRetryErrorKind;
  message: string;
  uncertain: boolean;
  refetchOrder: boolean;
  resumeUrl: string | null;
}

const REFUSAL_MESSAGES: Readonly<Record<string, string>> = {
  cash_order: PAYMENT_RETRY_MESSAGES.cashOrder,
  order_cancelled: PAYMENT_RETRY_MESSAGES.orderCancelled,
  order_not_payable: PAYMENT_RETRY_MESSAGES.notPayable,
  checkout_hold_expired: PAYMENT_RETRY_MESSAGES.holdExpired,
  offer_checkout_expired: PAYMENT_RETRY_MESSAGES.offerExpired,
};

function isApiError(value: unknown): value is ApiError {
  return typeof value === "object" && value !== null && "kind" in value && "message" in value;
}

function outcome(
  kind: PaymentRetryErrorKind,
  message: string,
  overrides: Partial<Omit<PaymentRetryErrorOutcome, "kind" | "message">> = {}
): PaymentRetryErrorOutcome {
  return { kind, message, uncertain: false, refetchOrder: false, resumeUrl: null, ...overrides };
}

function own(table: Readonly<Record<string, string>>, key: string | undefined): string | undefined {
  return key !== undefined && Object.prototype.hasOwnProperty.call(table, key) ? table[key] : undefined;
}

function formatWait(seconds: number): string {
  if (seconds >= 3600) {
    const hours = Math.round(seconds / 3600);
    return `${hours} hour${hours === 1 ? "" : "s"}`;
  }
  if (seconds >= 60) {
    const minutes = Math.round(seconds / 60);
    return `${minutes} minute${minutes === 1 ? "" : "s"}`;
  }
  return `${seconds} second${seconds === 1 ? "" : "s"}`;
}

function uncertain(): PaymentRetryErrorOutcome {
  return outcome("uncertain", PAYMENT_RETRY_MESSAGES.uncertain, { uncertain: true });
}

export function describePaymentRetryError(error: unknown): PaymentRetryErrorOutcome {
  if (!isApiError(error)) {
    // Thrown before any request was sent: nothing can have started.
    return outcome("message", PAYMENT_RETRY_MESSAGES.generic);
  }
  if (error.kind === "csrf") {
    // A local precondition: no request was sent.
    return outcome("message", PAYMENT_RETRY_MESSAGES.csrf);
  }
  if (error.kind !== "http" || error.status === undefined) {
    return uncertain();
  }

  switch (`${error.status} ${error.code ?? ""}`) {
    case "409 IDEMPOTENCY_REQUEST_IN_PROGRESS":
      return outcome("uncertain", PAYMENT_RETRY_MESSAGES.inProgress, { uncertain: true });
    case "409 PAYMENT_ALREADY_ACTIVE": {
      const url = readProblemString(error, "redirect_url") ?? null;
      const resumeUrl = isFollowableRedirect(url) ? url : null;
      return outcome(
        "already-active",
        resumeUrl ? PAYMENT_RETRY_MESSAGES.alreadyActiveResume : PAYMENT_RETRY_MESSAGES.alreadyActiveProcessing,
        { refetchOrder: true, resumeUrl }
      );
    }
    case "409 INVALID_STATE_TRANSITION":
      return outcome(
        "not-retryable",
        own(REFUSAL_MESSAGES, readProblemString(error, "reason")) ?? PAYMENT_RETRY_MESSAGES.notPayable,
        { refetchOrder: true }
      );
    case "409 IDEMPOTENCY_KEY_CONFLICT":
      return outcome("message", PAYMENT_RETRY_MESSAGES.keyConflict);
    case "502 PAYMENT_PROVIDER_UNAVAILABLE":
      return outcome("provider-unavailable", PAYMENT_RETRY_MESSAGES.providerUnavailable, { refetchOrder: true });
    case "422 PAYMENT_METHOD_NOT_ALLOWED": {
      const reason = readProblemString(error, "reason");
      return outcome(
        "message",
        reason === "provider_not_configured" || reason === "provider_required"
          ? PAYMENT_RETRY_MESSAGES.onlineUnavailable
          : PAYMENT_RETRY_MESSAGES.methodNotAllowed
      );
    }
    case "503 ONLINE_PAYMENT_UNAVAILABLE":
      return outcome("message", PAYMENT_RETRY_MESSAGES.onlineUnavailable);
    case "403 CSRF_INVALID":
      return outcome("message", PAYMENT_RETRY_MESSAGES.csrf);
    case "403 EMAIL_VERIFICATION_REQUIRED":
      return outcome("verify-email", PAYMENT_RETRY_MESSAGES.verifyEmail);
    case "401 AUTH_REQUIRED":
      return outcome("session-expired", PAYMENT_RETRY_MESSAGES.sessionExpired);
    case "404 NOT_FOUND":
      return outcome("message", PAYMENT_RETRY_MESSAGES.notFound, { refetchOrder: true });
    case "429 RATE_LIMITED":
      return outcome(
        "message",
        error.retryAfterSeconds !== undefined
          ? `Too many payment attempts. Please try again in ${formatWait(error.retryAfterSeconds)}.`
          : PAYMENT_RETRY_MESSAGES.rateLimited
      );
    default:
      return error.status >= 500 ? uncertain() : outcome("message", PAYMENT_RETRY_MESSAGES.generic);
  }
}
