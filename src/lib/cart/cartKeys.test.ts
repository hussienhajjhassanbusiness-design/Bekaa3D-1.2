import { describe, it, expect } from "vitest";
import { cartKeys } from "./cartKeys";

// FVS-025-IMPLEMENTATION-PLAN.md T01 — the ONE canonical cart query
// key (#ARCHITECTURE-CANONICAL-CART-QUERY). MiniCartDrawer, CartPage,
// checkout, and the product-page add-to-cart mutation must all share
// this key rather than each inventing a parallel cache for the same
// single, user-scoped cart.

describe("cartKeys", () => {
  it("has a stable root key", () => {
    expect(cartKeys.root).toEqual(["cart"]);
  });

  it("derives the current key from the canonical root", () => {
    expect(cartKeys.current()).toEqual(["cart", "current"]);
  });

  it("keeps the current key distinguishable from the bare root", () => {
    expect(cartKeys.current()).not.toEqual(cartKeys.root);
  });

  it("takes no arguments for current() — there is exactly one cart per user, not a per-id collection", () => {
    // @ts-expect-error — current() intentionally accepts no arguments
    expect(() => cartKeys.current("other")).not.toThrow();
  });
});
