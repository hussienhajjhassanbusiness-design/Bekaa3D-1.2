import type { ApiError } from "@/lib/api/ApiError";
import { readProblemArray, readProblemString } from "@/lib/api/problemExtensions";
import type { CheckoutFieldErrors, CheckoutFieldKey } from "./checkoutPayload";
import type { Money } from "./checkoutModel";

// #ARCHITECTURE-CHECKOUT-ERRORS
//
// Branches every POST /api/v1/checkout failure on status + Problem.code +
// typed extension members only (backend 2dfb27b ordering/api/checkout.py,
// docs/checkout.md "Errors"). All copy is frontend-owned: Problem.detail,
// Problem.title and ValidationError.msg are never returned.
//
// Two flags drive the page's safety rules:
//   uncertain - the server may or may not have placed the order (network,
//               timeout, 5xx, IDEMPOTENCY_REQUEST_IN_PROGRESS). The form is
//               locked and the only action is a retry of the SAME body with
//               the SAME Idempotency-Key, which replays the real outcome
//               instead of placing a second order. The cart is not refetched
//               (an emptied cart must not hide the pending attempt).
//   retireKey - the current key must not be reused (the order now exists
//               unpaid, or the key collided with a different body).
// Every other refusal happens before the order commits: the server leaves
// the cart, the orders and the key untouched.

export const CHECKOUT_MESSAGES = {
  generic: "Something went wrong placing your order. Your cart hasn't changed. Please try again.",
  uncertain:
    "We couldn't confirm whether your order was placed. Try again: it's safe, and it won't place a second order.",
  inProgress: "Your order is still being processed. Wait a moment, then check again.",
  priceChanged: "Some prices have changed since you added these items. Nothing has been charged.",
  linesRefused: "Some items in your cart can't be ordered right now. Nothing has been charged.",
  alreadyOwned:
    "You already own one or more of these STL files, or they're in another of your unpaid orders. Remove them from your cart to continue.",
  cartEmpty: "Your cart is empty, so there's nothing to order.",
  cartEmptyOwned: "Every STL file in your cart is one you already own, so there was nothing left to order.",
  invalidDetails: "Some of your checkout details are invalid. Please review them and try again.",
  invalidPhone: "Enter a valid Lebanese phone number.",
  addressRequired: "Choose a delivery address.",
  fulfillmentRequired: "Choose delivery or pickup.",
  paymentRequired: "Choose how you'd like to pay.",
  termsRequired: "Please accept the terms of sale to place your order.",
  digitalRequired: "Please confirm you understand that STL files are final sale.",
  cashTermsRequired: "Please accept the cash payment terms.",
  noteTooLong: "Notes can be at most 1000 characters.",
  invalidFulfillment:
    "The delivery or pickup details don't fit this order. Please choose your delivery address or pickup again.",
  cashNeedsPhysical: "Cash is only available when every item in your order is a physical product.",
  cashDisabled: "Cash payment isn't available right now. Please pay online.",
  zeroTotal: "This order can't be placed with this payment method. Please contact us for help.",
  paymentNotAllowed: "This payment method can't be used for this order.",
  cashLimit: "This order is above the limit for cash payment. Please pay online.",
  cashNotAvailable: "Cash on delivery isn't available for this order. Please pay online.",
  onlineUnavailable: "Online payment isn't available right now. Your cart has been kept.",
  ordersPaused: "The shop isn't accepting orders right now. Your cart has been kept.",
  keyConflict: "Your order details changed while it was being placed. Please review your order and place it again.",
  verifyEmail: "Verify your email address before placing an order.",
  csrf: "Unable to verify your session. Please refresh the page and try again.",
  sessionExpired: "Your session has expired. Please log in again to place your order.",
  rateLimited: "Too many checkout attempts. Please wait a while and try again.",
  paymentNotStarted: "Your order was created, but its payment couldn't be started, so nothing has been charged.",
} as const;

export interface PriceChangeLine {
  productId: string;
  oldAmountCents: number;
  newAmountCents: number;
  currency: string;
}

// `reason`: not_listed | unavailable | whatsapp_only | over_cap (kept as a
// string so a future reason still renders with a generic line).
export interface RefusedLine {
  productId: string;
  reason: string;
  maxQuantity: number | null;
}

interface OutcomeFlags {
  message: string;
  uncertain: boolean;
  retireKey: boolean;
  refetchCart: boolean;
  refetchSettings: boolean;
  refetchAddresses: boolean;
  refetchAuth: boolean;
}

export type CheckoutErrorOutcome = OutcomeFlags &
  (
    | { kind: "price-changed"; changes: PriceChangeLine[] }
    | { kind: "lines-refused"; lines: RefusedLine[] }
    | { kind: "already-owned"; productIds: string[] }
    | { kind: "cart-empty"; droppedProductIds: string[] }
    | { kind: "fields"; fieldErrors: CheckoutFieldErrors }
    | { kind: "payment-not-started"; orderId: string | null; orderNumber: string | null }
    | { kind: "verify-email" }
    | { kind: "session-expired" }
    | { kind: "message" }
  );

export interface CheckoutErrorContext {
  // PublicSettings cash_max_order_total, for the cash-limit copy only.
  cashMaxOrderTotal?: Money | null;
}

function flags(message: string, overrides: Partial<OutcomeFlags> = {}): OutcomeFlags {
  return {
    message,
    uncertain: false,
    retireKey: false,
    refetchCart: false,
    refetchSettings: false,
    refetchAddresses: false,
    refetchAuth: false,
    ...overrides,
  };
}

function isApiError(value: unknown): value is ApiError {
  return typeof value === "object" && value !== null && "kind" in value && "message" in value;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isInt(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

function priceChanges(error: ApiError): PriceChangeLine[] {
  return (readProblemArray(error, "price_changes") ?? []).flatMap((item) =>
    isRecord(item) &&
    typeof item.product_id === "string" &&
    isInt(item.old_amount_cents) &&
    isInt(item.new_amount_cents) &&
    typeof item.currency === "string"
      ? [
          {
            productId: item.product_id,
            oldAmountCents: item.old_amount_cents,
            newAmountCents: item.new_amount_cents,
            currency: item.currency,
          },
        ]
      : []
  );
}

function refusedLines(error: ApiError): RefusedLine[] {
  return (readProblemArray(error, "lines") ?? []).flatMap((item) =>
    isRecord(item) && typeof item.product_id === "string" && typeof item.reason === "string"
      ? [
          {
            productId: item.product_id,
            reason: item.reason,
            maxQuantity: isInt(item.max_quantity) ? item.max_quantity : null,
          },
        ]
      : []
  );
}

function stringIds(error: ApiError, key: string): string[] {
  return (readProblemArray(error, key) ?? []).filter((id): id is string => typeof id === "string");
}

function droppedIds(error: ApiError): string[] {
  return (readProblemArray(error, "dropped_lines") ?? []).flatMap((item) =>
    isRecord(item) && typeof item.product_id === "string" ? [item.product_id] : []
  );
}

const FIELD_BY_LOC: Readonly<Record<string, { field: CheckoutFieldKey; message: string }>> = {
  contact_phone: {
    field: "contactPhone",
    message: CHECKOUT_MESSAGES.invalidPhone,
  },
  address_id: {
    field: "addressId",
    message: CHECKOUT_MESSAGES.addressRequired,
  },
  fulfillment_method: {
    field: "fulfillment",
    message: CHECKOUT_MESSAGES.fulfillmentRequired,
  },
  payment_method: {
    field: "paymentMethod",
    message: CHECKOUT_MESSAGES.paymentRequired,
  },
  accept_terms: {
    field: "acceptTerms",
    message: CHECKOUT_MESSAGES.termsRequired,
  },
  accept_digital_final_sale: {
    field: "acceptDigitalFinalSale",
    message: CHECKOUT_MESSAGES.digitalRequired,
  },
  accept_cash_terms: {
    field: "acceptCashTerms",
    message: CHECKOUT_MESSAGES.cashTermsRequired,
  },
  customer_note: {
    field: "customerNote",
    message: CHECKOUT_MESSAGES.noteTooLong,
  },
};

function fieldErrors(error: ApiError): CheckoutFieldErrors {
  const result: CheckoutFieldErrors = {};
  for (const item of error.errors ?? []) {
    if (item.loc[0] !== "body") {
      continue;
    }
    const mapped = FIELD_BY_LOC[String(item.loc[1])];
    if (mapped && !result[mapped.field]) {
      result[mapped.field] = mapped.message;
    }
  }
  return result;
}

const PAYMENT_REASON_MESSAGES: Readonly<Record<string, string>> = {
  cash_requires_physical: CHECKOUT_MESSAGES.cashNeedsPhysical,
  cash_disabled: CHECKOUT_MESSAGES.cashDisabled,
  zero_total: CHECKOUT_MESSAGES.zeroTotal,
  provider_not_configured: CHECKOUT_MESSAGES.onlineUnavailable,
  provider_required: CHECKOUT_MESSAGES.onlineUnavailable,
  // The frontend never sends a provider with cash, so this is a bug.
  provider_not_applicable: CHECKOUT_MESSAGES.generic,
};

function formatMoney(money: Money): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: money.currency,
  }).format(money.amountCents / 100);
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

function uncertain(): CheckoutErrorOutcome {
  return {
    kind: "message",
    ...flags(CHECKOUT_MESSAGES.uncertain, { uncertain: true }),
  };
}

export function describeCheckoutError(error: unknown, context: CheckoutErrorContext = {}): CheckoutErrorOutcome {
  if (!isApiError(error)) {
    // Thrown before any request was sent: nothing can have been placed.
    return { kind: "message", ...flags(CHECKOUT_MESSAGES.generic) };
  }
  if (error.kind === "csrf") {
    return { kind: "message", ...flags(CHECKOUT_MESSAGES.csrf) };
  }
  if (error.kind !== "http" || error.status === undefined) {
    // network / timeout / unparseable body: the outcome is unknown.
    return uncertain();
  }

  switch (`${error.status} ${error.code ?? ""}`) {
    case "409 CART_PRICE_CHANGED":
      return {
        kind: "price-changed",
        changes: priceChanges(error),
        ...flags(CHECKOUT_MESSAGES.priceChanged, { refetchCart: true }),
      };
    case "422 PRODUCT_NOT_PURCHASABLE":
    case "422 QUANTITY_EXCEEDS_LIMIT":
      return {
        kind: "lines-refused",
        lines: refusedLines(error),
        ...flags(CHECKOUT_MESSAGES.linesRefused, { refetchCart: true }),
      };
    case "409 PRODUCT_ALREADY_OWNED":
      return {
        kind: "already-owned",
        productIds: stringIds(error, "product_ids"),
        ...flags(CHECKOUT_MESSAGES.alreadyOwned, { refetchCart: true }),
      };
    case "409 CART_EMPTY": {
      const dropped = droppedIds(error);
      return {
        kind: "cart-empty",
        droppedProductIds: dropped,
        ...flags(dropped.length > 0 ? CHECKOUT_MESSAGES.cartEmptyOwned : CHECKOUT_MESSAGES.cartEmpty, {
          refetchCart: true,
        }),
      };
    }
    case "422 VALIDATION_ERROR": {
      const fields = fieldErrors(error);
      if (Object.keys(fields).length === 0) {
        return { kind: "message", ...flags(CHECKOUT_MESSAGES.invalidDetails) };
      }
      return {
        kind: "fields",
        fieldErrors: fields,
        ...flags(CHECKOUT_MESSAGES.invalidDetails),
      };
    }
    case "422 INVALID_FULFILLMENT":
      return {
        kind: "message",
        ...flags(CHECKOUT_MESSAGES.invalidFulfillment, {
          refetchAddresses: true,
          refetchSettings: true,
        }),
      };
    case "422 PAYMENT_METHOD_NOT_ALLOWED": {
      const reason = readProblemString(error, "reason");
      const message = (reason && PAYMENT_REASON_MESSAGES[reason]) ?? CHECKOUT_MESSAGES.paymentNotAllowed;
      return {
        kind: "message",
        ...flags(message, { refetchSettings: reason === "cash_disabled" }),
      };
    }
    case "422 CASH_PAYMENT_LIMIT_REACHED": {
      const max = context.cashMaxOrderTotal;
      const message = max
        ? `This order is above the ${formatMoney(max)} limit for cash payment. Please pay online.`
        : CHECKOUT_MESSAGES.cashLimit;
      return { kind: "message", ...flags(message, { refetchSettings: true }) };
    }
    case "422 CASH_NOT_AVAILABLE":
      return { kind: "message", ...flags(CHECKOUT_MESSAGES.cashNotAvailable) };
    case "409 IDEMPOTENCY_REQUEST_IN_PROGRESS":
      return {
        kind: "message",
        ...flags(CHECKOUT_MESSAGES.inProgress, { uncertain: true }),
      };
    case "409 IDEMPOTENCY_KEY_CONFLICT":
      return {
        kind: "message",
        ...flags(CHECKOUT_MESSAGES.keyConflict, { retireKey: true }),
      };
    case "502 PAYMENT_PROVIDER_UNAVAILABLE":
      return {
        kind: "payment-not-started",
        orderId: readProblemString(error, "order_id") ?? null,
        orderNumber: readProblemString(error, "order_number") ?? null,
        ...flags(CHECKOUT_MESSAGES.paymentNotStarted, {
          retireKey: true,
          refetchCart: true,
        }),
      };
    case "503 ORDERS_PAUSED":
      return {
        kind: "message",
        ...flags(CHECKOUT_MESSAGES.ordersPaused, { refetchSettings: true }),
      };
    case "503 ONLINE_PAYMENT_UNAVAILABLE":
      return { kind: "message", ...flags(CHECKOUT_MESSAGES.onlineUnavailable) };
    case "403 EMAIL_VERIFICATION_REQUIRED":
      return {
        kind: "verify-email",
        ...flags(CHECKOUT_MESSAGES.verifyEmail, { refetchAuth: true }),
      };
    case "403 CSRF_INVALID":
      return { kind: "message", ...flags(CHECKOUT_MESSAGES.csrf) };
    case "401 AUTH_REQUIRED":
      return {
        kind: "session-expired",
        ...flags(CHECKOUT_MESSAGES.sessionExpired),
      };
    case "429 RATE_LIMITED":
      return {
        kind: "message",
        ...flags(
          error.retryAfterSeconds !== undefined
            ? `Too many checkout attempts. Please try again in ${formatWait(error.retryAfterSeconds)}.`
            : CHECKOUT_MESSAGES.rateLimited
        ),
      };
    default:
      return error.status >= 500 ? uncertain() : { kind: "message", ...flags(CHECKOUT_MESSAGES.generic) };
  }
}
