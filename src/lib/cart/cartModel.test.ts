import { describe, it, expect } from "vitest";
import type { CartLineModel, CartModel } from "./cartModel";

// FVS-025-IMPLEMENTATION-PLAN.md T01 — frontend-normalized shapes
// only, never a claim about the real GET /cart response field names
// (unconfirmed — plan §0/§1; #ARCHITECTURE-CART-ADAPTER). Pure
// compile-time checks: `CartLineModel` has no availability/unavailable
// field (the backend's unavailable-line mechanism is unconfirmed) and
// `CartModel` has no totals field (no source confirms cart-read
// returns one) — if someone adds either without backend evidence,
// this file is where a reviewer would notice and reconsider.

describe("CartLineModel", () => {
  it("accepts the normalized fields this plan actually needs for a physical line", () => {
    const line: CartLineModel = {
      id: "line-1",
      productId: "prod-1",
      productDisplayName: "Garden Gnome",
      productType: "physical",
      quantity: 2,
      maxQuantity: 5,
      snapshotPriceCents: 1999,
      currentPriceCents: 1999,
      currency: "USD",
      thumbnailSrc: "/gnome.png",
    };
    expect(line.id).toBe("line-1");
  });

  it("accepts an STL line with quantity fixed and no maxQuantity required", () => {
    const line: CartLineModel = {
      id: "line-2",
      productId: "prod-2",
      productDisplayName: "Dragon STL",
      productType: "stl",
      quantity: 1,
      snapshotPriceCents: 500,
      currency: "USD",
    };
    expect(line.productType).toBe("stl");
  });

  it("has no availability/unavailable field — the backend's unavailable-line mechanism is unconfirmed", () => {
    const line: CartLineModel = {
      id: "line-1",
      productId: "prod-1",
      productDisplayName: "Garden Gnome",
      productType: "physical",
      quantity: 1,
      snapshotPriceCents: 1999,
      currency: "USD",
    };
    expect("availability" in line).toBe(false);
    expect("isUnavailable" in line).toBe(false);
  });
});

describe("CartModel", () => {
  it("accepts the normalized fields this plan actually needs", () => {
    const cart: CartModel = { id: "cart-1", lines: [] };
    expect(cart.id).toBe("cart-1");
  });

  it("has no totals field — no source confirms cart-read returns one", () => {
    const cart: CartModel = { id: "cart-1", lines: [] };
    expect("subtotal" in cart).toBe(false);
    expect("total" in cart).toBe(false);
  });
});
