import type { ApiError } from "@/lib/api/ApiError";
import { readProblemString } from "@/lib/api/problemExtensions";
import { isFollowableRedirect } from "@/lib/checkout/checkoutModel";
import { formatOrderDateTime } from "@/lib/orders/orderFormat";
import { formatMoney } from "./offerModel";

// #FVS-OFFERS-ERRORS (phase 6C)
//
// Every offer write failure, branched on status + Problem.code + the typed
// extension members the backend documents (negotiation/api/offer_errors.py,
// ordering/api/offer_checkout.py). Problem.title/detail and validation `msg`
// are never returned; all copy is frontend-owned.
//
//   refetchOffer   - the offer moved on server-side (someone answered, it
//                    expired, the amount changed): re-read the canonical
//                    detail so the page shows the real state and actions.
//   refetchProduct - the product stopped being offerable.
//   refetchAuth    - EMAIL_VERIFICATION_REQUIRED: the session's verified
//                    flag is stale.
//   field          - a field-level message for the amount or the message.

export const OFFER_MESSAGES = {
  generic: "Something went wrong. Please try again.",
  uncertainCreate:
    "We couldn't confirm whether your offer was sent. Check your offers before sending it again.",
  uncertainAnswer: "We couldn't confirm whether your reply went through. The latest state of the offer is shown.",
  csrf: "Unable to verify your session. Please refresh the page and try again.",
  verifyEmail: "Verify your email address before making or answering offers.",
  sessionExpired: "Your session has expired. Please sign in again.",
  alreadyActive: "You already have an offer in progress on this product.",
  owned: "You already own this STL, so there's nothing to offer on.",
  notOfferable: "Offers aren't open on this product right now.",
  belowMinimum: "This offer is below the lowest amount we can accept for this product.",
  aboveList: "An offer can't be more than the product's current price.",
  amountInvalid: "Enter a valid amount.",
  messageTooLong: "Messages can be at most 1000 characters.",
  cooldown: "A recent offer on this product was declined, so you can't make a new one yet.",
  paused: "The shop isn't accepting offers right now. Please try again later.",
  notYourTurn: "The other side has to reply before this offer can be answered. The latest state is shown.",
  movedOn: "This offer has already moved on, so that's no longer possible. The latest state is shown.",
  amountChanged: "The amount on the table changed, so nothing was accepted. Review the new amount.",
  expired: "The reply deadline for this offer has passed, so it has expired.",
  notFound: "We couldn't find this offer.",
  rateLimited: "Too many offer actions. Please wait a while and try again.",
  serviceUnavailable: "This service is temporarily unavailable. Please try again shortly.",
} as const;

export interface OfferErrorOutcome {
  kind: "message" | "already-active" | "verify-email" | "session-expired" | "not-found";
  message: string;
  field?: { name: "amount" | "message"; message: string };
  refetchOffer: boolean;
  refetchProduct: boolean;
  refetchAuth: boolean;
}

function isApiError(value: unknown): value is ApiError {
  return typeof value === "object" && value !== null && "kind" in value;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
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

function outcome(message: string, overrides: Partial<OfferErrorOutcome> = {}): OfferErrorOutcome {
  return { kind: "message", message, refetchOffer: false, refetchProduct: false, refetchAuth: false, ...overrides };
}

function priceMember(error: ApiError, key: string): string | null {
  const raw = error.raw;
  if (!isRecord(raw)) return null;
  const value = raw[key];
  if (isRecord(value) && Number.isInteger(value.amount_cents) && typeof value.currency === "string") {
    return formatMoney({ amount_cents: value.amount_cents as number, currency: value.currency });
  }
  return null;
}

function validationOutcome(error: ApiError): OfferErrorOutcome {
  for (const item of error.errors ?? []) {
    if (item.loc[0] !== "body") continue;
    const loc = String(item.loc[1]);
    if (loc === "amount_cents") {
      // The only amount refusal that reaches VALIDATION_ERROR past the
      // client's own checks is "above the list price" (offer_errors.py).
      return outcome(OFFER_MESSAGES.aboveList, {
        field: { name: "amount", message: OFFER_MESSAGES.aboveList },
        refetchProduct: true,
      });
    }
    if (loc === "message" || loc === "reason") {
      return outcome(OFFER_MESSAGES.messageTooLong, { field: { name: "message", message: OFFER_MESSAGES.messageTooLong } });
    }
  }
  return outcome(OFFER_MESSAGES.generic);
}

// `operation`: "create" opens an offer; "answer" is counter / accept /
// withdraw (customer) or counter / accept / reject (admin).
export function describeOfferError(error: unknown, operation: "create" | "answer"): OfferErrorOutcome {
  const uncertain =
    operation === "create"
      ? outcome(OFFER_MESSAGES.uncertainCreate)
      : outcome(OFFER_MESSAGES.uncertainAnswer, { refetchOffer: true });
  if (!isApiError(error)) return outcome(OFFER_MESSAGES.generic);
  if (error.kind === "csrf") return outcome(OFFER_MESSAGES.csrf);
  if (error.kind !== "http" || error.status === undefined) return uncertain;

  switch (`${error.status} ${error.code ?? ""}`) {
    case "403 CSRF_INVALID":
      return outcome(OFFER_MESSAGES.csrf);
    case "403 EMAIL_VERIFICATION_REQUIRED":
      return outcome(OFFER_MESSAGES.verifyEmail, { kind: "verify-email", refetchAuth: true });
    case "401 AUTH_REQUIRED":
      return outcome(OFFER_MESSAGES.sessionExpired, { kind: "session-expired" });
    case "409 OFFER_ALREADY_ACTIVE":
      return outcome(OFFER_MESSAGES.alreadyActive, { kind: "already-active" });
    case "409 PRODUCT_ALREADY_OWNED":
      return outcome(OFFER_MESSAGES.owned, { refetchOffer: operation === "answer", refetchProduct: true });
    case "422 PRODUCT_NOT_PURCHASABLE":
      return outcome(OFFER_MESSAGES.notOfferable, { refetchOffer: operation === "answer", refetchProduct: true });
    case "422 OFFER_BELOW_MINIMUM": {
      const minimum = priceMember(error, "minimum");
      const message = minimum
        ? `The lowest offer we can accept for this product is ${minimum}.`
        : OFFER_MESSAGES.belowMinimum;
      return outcome(message, { field: { name: "amount", message } });
    }
    case "422 OFFER_COOLDOWN_ACTIVE": {
      const until = readProblemString(error, "cooldown_until");
      const valid = until !== undefined && !Number.isNaN(new Date(until).getTime());
      return outcome(
        valid ? `A recent offer on this product was declined. You can make a new offer after ${formatOrderDateTime(until)}.` : OFFER_MESSAGES.cooldown
      );
    }
    case "422 VALIDATION_ERROR":
      return validationOutcome(error);
    case "503 ORDERS_PAUSED":
      return outcome(OFFER_MESSAGES.paused);
    case "503 SERVICE_UNAVAILABLE":
      return outcome(OFFER_MESSAGES.serviceUnavailable);
    case "409 OFFER_NOT_YOUR_TURN":
      return outcome(OFFER_MESSAGES.notYourTurn, { refetchOffer: true });
    case "409 INVALID_STATE_TRANSITION":
      return outcome(OFFER_MESSAGES.movedOn, { refetchOffer: true });
    case "409 OFFER_AMOUNT_CHANGED": {
      const current = priceMember(error, "current_amount");
      return outcome(
        current ? `The amount on the table is now ${current}, so nothing was accepted. Review it and try again.` : OFFER_MESSAGES.amountChanged,
        { refetchOffer: true }
      );
    }
    case "410 OFFER_EXPIRED":
      return outcome(OFFER_MESSAGES.expired, { refetchOffer: true });
    case "404 NOT_FOUND":
      return outcome(OFFER_MESSAGES.notFound, { kind: "not-found" });
    case "429 RATE_LIMITED":
      return outcome(
        error.retryAfterSeconds !== undefined
          ? `Too many offer actions. Please try again in ${formatWait(error.retryAfterSeconds)}.`
          : OFFER_MESSAGES.rateLimited
      );
    default:
      return error.status >= 500 ? uncertain : outcome(OFFER_MESSAGES.generic);
  }
}

// --- offer checkout ---------------------------------------------------------
//
// POST /me/offers/{id}/checkout reuses cart checkout's idempotency rules
// (checkoutIdempotency.ts):
//   uncertain - the order may or may not exist (network, timeout, 5xx,
//               IDEMPOTENCY_REQUEST_IN_PROGRESS): only a same-key retry is
//               offered, which replays the real outcome.
//   retireKey - the key must not be reused (the order now exists unpaid, or
//               the key collided with a different body).

export const OFFER_CHECKOUT_MESSAGES = {
  generic: "Something went wrong starting your checkout. Nothing has been charged. Please try again.",
  uncertain:
    "We couldn't confirm whether your order was placed. Try again: it's safe, and it won't place a second order.",
  inProgress: "Your order is still being processed. Wait a moment, then try again.",
  windowEnded: "The checkout window for this offer has ended, so it can no longer be bought at the agreed price.",
  notAccepted: "This offer can't be checked out in its current state. The latest state is shown.",
  alreadyActive: "A payment for this offer's order is already in progress. You can continue it.",
  alreadyActiveProcessing:
    "A payment for this offer's order is already being processed. Check your orders for its result.",
  owned:
    "You already own this STL, or it's waiting in another of your unpaid orders. Check your orders to complete that payment.",
  notPurchasable: "This product can't be bought right now. Nothing has been charged.",
  termsRequired: "Please accept the terms of sale and confirm that STL files are final sale.",
  paused: "The shop isn't accepting orders right now. Your accepted offer is kept until its checkout window ends.",
  onlineUnavailable: "Online payment isn't available right now. Your accepted offer is kept until its checkout window ends.",
  methodNotAllowed: "Online payment can't be used for this order.",
  keyConflict: "Something changed while your order was being placed. Please try again.",
  paymentNotStarted: "Your order was created, but its payment couldn't be started, so nothing has been charged.",
  csrf: OFFER_MESSAGES.csrf,
  verifyEmail: "Verify your email address before checking out.",
  sessionExpired: OFFER_MESSAGES.sessionExpired,
  notFound: OFFER_MESSAGES.notFound,
  rateLimited: "Too many checkout attempts. Please wait a while and try again.",
} as const;

export type OfferCheckoutErrorOutcome =
  | { kind: "uncertain"; message: string }
  | { kind: "payment-not-started"; message: string; orderId: string | null; orderNumber: string | null }
  | { kind: "already-active"; message: string; resumeUrl: string | null }
  | {
      kind: "message" | "verify-email" | "session-expired" | "owned";
      message: string;
      retireKey: boolean;
      refetchOffer: boolean;
      refetchAuth: boolean;
    };

function checkoutMessage(
  message: string,
  overrides: Partial<{ kind: "message" | "verify-email" | "session-expired" | "owned"; retireKey: boolean; refetchOffer: boolean; refetchAuth: boolean }> = {}
): OfferCheckoutErrorOutcome {
  return { kind: "message", message, retireKey: false, refetchOffer: false, refetchAuth: false, ...overrides };
}

export function describeOfferCheckoutError(error: unknown): OfferCheckoutErrorOutcome {
  if (!isApiError(error)) return checkoutMessage(OFFER_CHECKOUT_MESSAGES.generic);
  if (error.kind === "csrf") return checkoutMessage(OFFER_CHECKOUT_MESSAGES.csrf);
  if (error.kind !== "http" || error.status === undefined) {
    return { kind: "uncertain", message: OFFER_CHECKOUT_MESSAGES.uncertain };
  }

  switch (`${error.status} ${error.code ?? ""}`) {
    case "410 OFFER_CHECKOUT_EXPIRED":
      return checkoutMessage(OFFER_CHECKOUT_MESSAGES.windowEnded, { refetchOffer: true });
    case "409 INVALID_STATE_TRANSITION":
      return checkoutMessage(OFFER_CHECKOUT_MESSAGES.notAccepted, { refetchOffer: true });
    case "409 PAYMENT_ALREADY_ACTIVE": {
      const url = readProblemString(error, "redirect_url") ?? null;
      const resumeUrl = isFollowableRedirect(url) ? url : null;
      return {
        kind: "already-active",
        message: resumeUrl ? OFFER_CHECKOUT_MESSAGES.alreadyActive : OFFER_CHECKOUT_MESSAGES.alreadyActiveProcessing,
        resumeUrl,
      };
    }
    case "409 PRODUCT_ALREADY_OWNED":
      return checkoutMessage(OFFER_CHECKOUT_MESSAGES.owned, { kind: "owned", refetchOffer: true });
    case "422 PRODUCT_NOT_PURCHASABLE":
      return checkoutMessage(OFFER_CHECKOUT_MESSAGES.notPurchasable, { refetchOffer: true });
    case "422 VALIDATION_ERROR":
      return checkoutMessage(OFFER_CHECKOUT_MESSAGES.termsRequired);
    case "422 PAYMENT_METHOD_NOT_ALLOWED":
      return checkoutMessage(OFFER_CHECKOUT_MESSAGES.methodNotAllowed);
    case "409 IDEMPOTENCY_REQUEST_IN_PROGRESS":
      return { kind: "uncertain", message: OFFER_CHECKOUT_MESSAGES.inProgress };
    case "409 IDEMPOTENCY_KEY_CONFLICT":
      return checkoutMessage(OFFER_CHECKOUT_MESSAGES.keyConflict, { retireKey: true });
    case "502 PAYMENT_PROVIDER_UNAVAILABLE":
      return {
        kind: "payment-not-started",
        message: OFFER_CHECKOUT_MESSAGES.paymentNotStarted,
        orderId: readProblemString(error, "order_id") ?? null,
        orderNumber: readProblemString(error, "order_number") ?? null,
      };
    case "503 ORDERS_PAUSED":
      return checkoutMessage(OFFER_CHECKOUT_MESSAGES.paused);
    case "503 ONLINE_PAYMENT_UNAVAILABLE":
      return checkoutMessage(OFFER_CHECKOUT_MESSAGES.onlineUnavailable);
    case "403 CSRF_INVALID":
      return checkoutMessage(OFFER_CHECKOUT_MESSAGES.csrf);
    case "403 EMAIL_VERIFICATION_REQUIRED":
      return checkoutMessage(OFFER_CHECKOUT_MESSAGES.verifyEmail, { kind: "verify-email", refetchAuth: true });
    case "401 AUTH_REQUIRED":
      return checkoutMessage(OFFER_CHECKOUT_MESSAGES.sessionExpired, { kind: "session-expired" });
    case "404 NOT_FOUND":
      return checkoutMessage(OFFER_CHECKOUT_MESSAGES.notFound, { refetchOffer: true });
    case "429 RATE_LIMITED":
      return checkoutMessage(
        error.retryAfterSeconds !== undefined
          ? `Too many checkout attempts. Please try again in ${formatWait(error.retryAfterSeconds)}.`
          : OFFER_CHECKOUT_MESSAGES.rateLimited
      );
    default:
      return error.status >= 500
        ? { kind: "uncertain", message: OFFER_CHECKOUT_MESSAGES.uncertain }
        : checkoutMessage(OFFER_CHECKOUT_MESSAGES.generic);
  }
}
