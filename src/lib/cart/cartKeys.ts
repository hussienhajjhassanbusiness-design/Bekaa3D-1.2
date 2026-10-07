// #ARCHITECTURE-CANONICAL-CART-QUERY
//
// The ONE canonical query key for the single, user-scoped cart
// resource. `MiniCartDrawer`, `CartPage`, checkout, and the
// product-page add-to-cart mutation MUST share this key rather than
// each inventing a parallel cache for the same cart
// (FVS-025-IMPLEMENTATION-PLAN.md §0/T01).
//
// `.current()` rather than `.list()`/`.detail(id)`: there is exactly
// one cart per user (VS-020's own "one persistent cart per user, no
// guest cart" rule) — mirrors `publicSettingsKeys`'s precedent for a
// singleton resource.
export const cartKeys = {
  root: ["cart"] as const,
  current: () => [...cartKeys.root, "current"] as const,
};
