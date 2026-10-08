import type { OrderListFilters } from "./orderModel";

// #ARCHITECTURE-CANONICAL-ORDERS-QUERY
//
// The ONE canonical query-key family for the customer order resource.
// If the backend later confirms GET /me/orders/{id} is ALSO FVS-027's
// authoritative payment-verification read, FVS-027 MUST invalidate
// orderKeys.detail(id) rather than inventing a second, parallel
// payment/order cache for the same backend truth
// (FVS-029-IMPLEMENTATION-PLAN.md §0/T01, resolving the gate FVS-027
// deliberately left open).
//
// Keys carry order id (and the normalized filter state for list())
// only — never address/customer PII, never a payment-provider
// reference. `filters` is embedded directly as a key segment; a
// consistent object shape is already deterministic under TanStack
// Query's own key-hashing, so no extra manual canonicalization step
// is needed.
export const orderKeys = {
  root: ["orders"] as const,
  list: (filters: OrderListFilters) => [...orderKeys.root, "list", filters] as const,
  detail: (orderId: string) => [...orderKeys.root, "detail", orderId] as const,
};
