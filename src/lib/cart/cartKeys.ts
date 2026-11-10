// #ARCHITECTURE-CANONICAL-CART-QUERY
//
// The ONE canonical query-key family for the cart. /cart, the header
// indicator and the product-page Add to cart all share `current(userId)`;
// FVS-026 checkout must reuse it rather than keep its own cart cache.
//
// One cart per user (backend VS-022), so `current` is a singleton per
// user. The user id is part of the key so a user switch in the same tab
// can never render the previous user's cached cart, even before logout
// cleanup runs. Every cart write invalidates `root`, and logout removes
// `root` (userScopedQueries.ts).
export const cartKeys = {
  root: ["cart"] as const,
  current: (userId: string) => [...cartKeys.root, "current", userId] as const,
};
