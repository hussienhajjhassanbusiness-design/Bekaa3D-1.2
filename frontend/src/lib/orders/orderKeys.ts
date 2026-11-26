// #ARCHITECTURE-CANONICAL-ORDERS-QUERY
//
// The ONE canonical query-key family for the customer's own orders
// (GET /api/v1/me/orders, GET /api/v1/me/orders/{id}). FVS-027 (payment
// result) and FVS-031 (cancel / confirm receipt / report problem) MUST
// read and invalidate these keys, never a parallel payment/order cache:
// the order detail is the backend's customer-facing payment truth
// (CURRENT-BACKEND-DRIFT-AUDIT.md: there is no customer payment route).
//
// User scoping: the whole `root` is dropped on logout, on a cross-tab
// logout and before every new sign-in (userScopedQueries.ts), so one
// user's orders are never served from cache to another.
//
// Keys carry the order id and the list's page size only — never address,
// phone or payment-provider data.
export interface OrderListParams {
  limit?: number;
}

export const orderKeys = {
  root: ["orders"] as const,
  lists: () => [...orderKeys.root, "list"] as const,
  list: (params: OrderListParams) => [...orderKeys.lists(), params] as const,
  detail: (orderId: string) => [...orderKeys.root, "detail", orderId] as const,
};
