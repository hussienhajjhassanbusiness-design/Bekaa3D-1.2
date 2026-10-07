import { describe, it, expect } from "vitest";
import { beginQuantityChange, beginRemoval, rollback, settle } from "./cartOptimistic";
import type { CartModel } from "./cartModel";

// FVS-025-IMPLEMENTATION-PLAN.md T07 — mirrors FVS-023's
// addressDefaultOptimistic.ts precedent exactly. Pure, contract-
// independent helpers only — no endpoint, body, or status code is
// invented. `settle` always adopts the authoritative cart verbatim,
// never the optimistic guess (server-truth reconciliation).

const CART: CartModel = {
  id: "cart-1",
  lines: [
    { id: "line-1", productId: "prod-1", productDisplayName: "Garden Gnome", productType: "physical", quantity: 2, snapshotPriceCents: 1000, currency: "USD" },
    { id: "line-2", productId: "prod-2", productDisplayName: "Dragon STL", productType: "stl", quantity: 1, snapshotPriceCents: 500, currency: "USD" },
  ],
};

describe("beginQuantityChange", () => {
  it("updates a physical line's quantity optimistically", () => {
    const result = beginQuantityChange(CART, "line-1", 5);
    expect(result.cart.lines.find((l) => l.id === "line-1")?.quantity).toBe(5);
  });

  it("never mutates the input cart", () => {
    const original = JSON.parse(JSON.stringify(CART));
    beginQuantityChange(CART, "line-1", 5);
    expect(CART).toEqual(original);
  });

  it("sets pendingLineId to the changed line", () => {
    const result = beginQuantityChange(CART, "line-1", 5);
    expect(result.pendingLineId).toBe("line-1");
  });

  it("is a no-op for an STL line — quantity is structurally fixed at 1", () => {
    const result = beginQuantityChange(CART, "line-2", 3);
    expect(result.cart).toEqual(CART);
    expect(result.pendingLineId).toBeNull();
  });
});

describe("beginRemoval", () => {
  it("optimistically removes the targeted line", () => {
    const result = beginRemoval(CART, "line-1");
    expect(result.cart.lines.find((l) => l.id === "line-1")).toBeUndefined();
    expect(result.cart.lines).toHaveLength(1);
  });

  it("sets pendingLineId to the removed line", () => {
    const result = beginRemoval(CART, "line-1");
    expect(result.pendingLineId).toBe("line-1");
  });
});

describe("rollback", () => {
  it("restores the exact previous snapshot and clears pendingLineId", () => {
    const result = rollback(CART);
    expect(result.cart).toEqual(CART);
    expect(result.pendingLineId).toBeNull();
  });
});

describe("settle", () => {
  it("adopts the authoritative cart verbatim, even when it differs from the optimistic guess", () => {
    const authoritative: CartModel = {
      id: "cart-1",
      lines: [{ ...CART.lines[0]!, quantity: 1 }],
    };
    const result = settle(authoritative);
    expect(result.cart).toEqual(authoritative);
    expect(result.pendingLineId).toBeNull();
  });
});
