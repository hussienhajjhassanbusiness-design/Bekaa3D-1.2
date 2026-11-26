import type { ApiError } from "@/lib/api/ApiError";
import { readProblemInteger, readProblemString } from "@/lib/api/problemExtensions";

// Error branching for every cart write (POST/PATCH/DELETE), on status +
// code + typed extension members only. The codes and extensions are the
// ones backend 2dfb27b actually returns (src/app/ordering/api/cart.py
// `_translate`, identity CSRF/verification dependencies, the shared rate
// limiter). Every string here is frontend-owned: Problem.detail/title and
// ValidationError.msg are never returned, so they can never be rendered.

export interface CartWriteErrorDescription {
  message: string;
  // The cart as shown may be stale (the line is gone, or the product is no
  // longer purchasable / its cap changed): refetch the canonical cart.
  refetch: boolean;
}

export const CART_MESSAGES = {
  generic: "Something went wrong updating your cart. Please try again.",
  unavailable: "This product is currently unavailable and can't be added to your cart.",
  whatsappOnly: "This product can only be ordered through WhatsApp.",
  notListed: "This product is no longer available.",
  notPurchasable: "This product can't be bought online right now.",
  quantityLimit: "That quantity is above the limit for this product.",
  // Stabilization: a limit of 1 applies to STL files AND to physical products
  // whose max_quantity_per_line is 1, so the copy must not claim "STL".
  singleCopy: "Only one of this item can be in your cart, and it's already there.",
  lineLimit: "Your cart is full. Remove a product to add another.",
  alreadyOwned: "You already own this STL file, so it can't be added again.",
  lineGone: "This item is no longer in your cart. Your cart has been refreshed.",
  verifyEmail: "Verify your email address to add or change items in your cart, or to check out.",
  csrf: "Unable to verify your session. Please refresh the page and try again.",
  authRequired: "Your session has expired. Please log in again.",
  rateLimited: "Too many cart changes. Please wait a while and try again.",
  invalidQuantity: "Choose a whole-number quantity of at least 1.",
} as const;

function isApiError(value: unknown): value is ApiError {
  return typeof value === "object" && value !== null && "kind" in value;
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

const REFUSAL_MESSAGES: Readonly<Record<string, string>> = {
  unavailable: CART_MESSAGES.unavailable,
  whatsapp_only: CART_MESSAGES.whatsappOnly,
  not_listed: CART_MESSAGES.notListed,
};

function describeQuantityLimit(error: ApiError): string {
  const max = readProblemInteger(error, "max_quantity");
  if (max === undefined || max < 1) {
    return CART_MESSAGES.quantityLimit;
  }
  if (max === 1) {
    return CART_MESSAGES.singleCopy;
  }
  const current = readProblemInteger(error, "current_quantity");
  const base = `You can have at most ${max} of this product in your cart.`;
  return current !== undefined && current > 0 ? `${base} You already have ${current}.` : base;
}

function result(message: string, refetch = false): CartWriteErrorDescription {
  return { message, refetch };
}

export function describeCartWriteError(error: unknown): CartWriteErrorDescription {
  if (!isApiError(error)) {
    return result(CART_MESSAGES.generic);
  }
  if (error.kind === "csrf") {
    return result(CART_MESSAGES.csrf);
  }
  if (error.kind !== "http") {
    return result(CART_MESSAGES.generic);
  }

  switch (`${error.status} ${error.code}`) {
    case "422 PRODUCT_NOT_PURCHASABLE": {
      const reason = readProblemString(error, "reason");
      return result((reason && REFUSAL_MESSAGES[reason]) ?? CART_MESSAGES.notPurchasable, true);
    }
    case "422 QUANTITY_EXCEEDS_LIMIT":
      return result(describeQuantityLimit(error), true);
    case "422 CART_LINE_LIMIT_REACHED": {
      const limit = readProblemInteger(error, "limit");
      return result(
        limit !== undefined && limit > 0
          ? `Your cart can hold up to ${limit} different products. Remove one to add another.`
          : CART_MESSAGES.lineLimit
      );
    }
    case "422 VALIDATION_ERROR":
      return result(CART_MESSAGES.invalidQuantity);
    case "409 PRODUCT_ALREADY_OWNED":
      return result(CART_MESSAGES.alreadyOwned);
    case "404 NOT_FOUND":
      return result(CART_MESSAGES.lineGone, true);
    case "403 EMAIL_VERIFICATION_REQUIRED":
      return result(CART_MESSAGES.verifyEmail);
    case "403 CSRF_INVALID":
      return result(CART_MESSAGES.csrf);
    case "401 AUTH_REQUIRED":
      return result(CART_MESSAGES.authRequired);
    case "429 RATE_LIMITED":
      return result(
        error.retryAfterSeconds !== undefined
          ? `Too many cart changes. Try again in ${formatWait(error.retryAfterSeconds)}.`
          : CART_MESSAGES.rateLimited
      );
    default:
      return result(CART_MESSAGES.generic);
  }
}
