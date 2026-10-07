// #ARCHITECTURE-CANONICAL-ENTITLEMENTS-QUERY
//
// The ONE canonical query-key family for the entitlement server
// resource — FVS-019's manual grant and any future payment-driven
// grant/revocation event MUST invalidate `entitlementKeys.root` (or
// `.list()`) rather than inventing a parallel `libraryQueryKey`/
// `ownedProductsQueryKey` for the same underlying data
// (FVS-020-IMPLEMENTATION-PLAN.md §0, resolving the gate FVS-019
// deliberately left open).
//
// `list()` takes no page/cursor argument: whether `/me/entitlements`
// is paginated is unconfirmed (plan §1) — baking a page argument into
// the key now would invent a pagination contract. The root/list key
// stays stable and parameterless; a cursor/page argument can be added
// later without changing this file's exported shape if backend
// evidence ever confirms pagination.
export const entitlementKeys = {
  root: ["entitlements"] as const,
  list: () => [...entitlementKeys.root, "list"] as const,
  detail: (entitlementId: string) => [...entitlementKeys.root, "detail", entitlementId] as const,
};
