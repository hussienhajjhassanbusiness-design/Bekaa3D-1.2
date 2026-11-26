import type { ApiError } from "@/lib/api/ApiError";

// #FVS029-ORDER-ERRORS
//
// Classifies a failed order read by status + `code` only — never by the
// backend's title/detail/msg text, which is never shown. The copy below is
// frontend-owned.
//
// Not found: 404 NOT_FOUND is the same body for an unknown id and for
// another customer's order (ownership is in every SQL query), so the page
// says the same thing for both. A 422 on the detail route can only mean a
// malformed id, which is the same "no such order" to a customer.
export type OrderErrorKind = "not-found" | "auth" | "generic";

function isApiError(error: unknown): error is ApiError {
  return typeof error === "object" && error !== null && "kind" in error;
}

export function classifyOrderError(error: unknown): OrderErrorKind {
  if (!isApiError(error) || error.kind !== "http") {
    return "generic";
  }
  if (error.status === 401) {
    return "auth";
  }
  if (error.status === 404 || error.status === 422) {
    return "not-found";
  }
  return "generic";
}

export const ORDER_ERROR_COPY = {
  listFailed: "We couldn't load your orders. Please try again.",
  detailFailed: "We couldn't load this order. Please try again.",
  sessionExpired: "Your session has expired. Please sign in again to see your orders.",
  notFoundTitle: "Order not found",
  notFoundBody: "We couldn't find this order in your account. Check the link, or find it in your order history.",
  loadMoreFailed: "We couldn't load more orders. Please try again.",
} as const;
