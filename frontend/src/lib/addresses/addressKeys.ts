// #ARCHITECTURE-CANONICAL-ADDRESSES-QUERY
//
// The ONE canonical query-key family for the customer address-book
// resource — FVS-026 checkout MUST reuse/invalidate `addressKeys.root`
// (or `.list()`) rather than inventing a checkout-local address cache
// for the same underlying data (FVS-023-IMPLEMENTATION-PLAN.md §0,
// mirroring the precedent `publicSettingsKeys` already set for its
// own resource).
//
// `list()` takes no page/cursor argument: the real `GET /me/addresses`
// is hard-capped (MAX_LIVE_ADDRESSES), not paginated (VS-026 Q6). Every
// address write invalidates `root` (useAddresses.ts), and the root is
// dropped on logout (userScopedQueries.ts).
//
// #SECURITY-CUSTOMER-ADDRESS — keys carry resource/id only, never
// address content (name/phone/street/etc.); addresses are personal
// information and must never appear in a cache key, URL, or log line.
export const addressKeys = {
  root: ["addresses"] as const,
  list: () => [...addressKeys.root, "list"] as const,
  detail: (addressId: string) => [...addressKeys.root, "detail", addressId] as const,
};
