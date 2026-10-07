// #ARCHITECTURE-CANONICAL-ADDRESSES-QUERY
//
// The ONE canonical query-key family for the customer address-book
// resource — FVS-026 checkout MUST reuse/invalidate `addressKeys.root`
// (or `.list()`) rather than inventing a checkout-local address cache
// for the same underlying data (FVS-023-IMPLEMENTATION-PLAN.md §0,
// mirroring the precedent `entitlementKeys`/`publicSettingsKeys`
// already set for their own resources).
//
// `list()` takes no page/cursor argument: whether `/me/addresses` is
// paginated is unconfirmed (plan §1) — baking a page argument into the
// key now would invent a pagination contract.
//
// #SECURITY-CUSTOMER-ADDRESS — keys carry resource/id only, never
// address content (name/phone/street/etc.); addresses are personal
// information and must never appear in a cache key, URL, or log line.
export const addressKeys = {
  root: ["addresses"] as const,
  list: () => [...addressKeys.root, "list"] as const,
  detail: (addressId: string) => [...addressKeys.root, "detail", addressId] as const,
};
