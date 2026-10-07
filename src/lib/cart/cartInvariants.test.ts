import { describe, it, expect } from "vitest";
import { isStlLine, canAdjustQuantity, hasPriceChanged, canAddStlGivenOwnership } from "./cartInvariants";
import type { CartLineModel } from "./cartModel";

// FVS-025-IMPLEMENTATION-PLAN.md T02 — small, pure helpers only. Every
// one of these is explicitly a UX nicety, never a security boundary
// (#SECURITY-CART-SERVER-AUTHORITY) — a stale/incomplete client cache
// must never be treated as authorization; the server is the final
// word regardless of what these return.

function makeLine(overrides: Partial<CartLineModel> = {}): CartLineModel {
  return {
    id: "line-1",
    productId: "prod-1",
    productDisplayName: "Garden Gnome",
    productType: "physical",
    quantity: 1,
    snapshotPriceCents: 1000,
    currency: "USD",
    ...overrides,
  };
}

describe("isStlLine", () => {
  it("is true for an STL line", () => {
    expect(isStlLine(makeLine({ productType: "stl" }))).toBe(true);
  });

  it("is false for a physical line", () => {
    expect(isStlLine(makeLine({ productType: "physical" }))).toBe(false);
  });
});

describe("canAdjustQuantity", () => {
  it("is true for a physical line", () => {
    expect(canAdjustQuantity(makeLine({ productType: "physical" }))).toBe(true);
  });

  it("is false for an STL line — quantity is always fixed at 1, no stepper ever", () => {
    expect(canAdjustQuantity(makeLine({ productType: "stl" }))).toBe(false);
  });
});

describe("hasPriceChanged", () => {
  it("is false when currentPriceCents is absent", () => {
    expect(hasPriceChanged(makeLine({ currentPriceCents: undefined }))).toBe(false);
  });

  it("is false when currentPriceCents equals snapshotPriceCents", () => {
    expect(hasPriceChanged(makeLine({ snapshotPriceCents: 1000, currentPriceCents: 1000 }))).toBe(false);
  });

  it("is true when currentPriceCents differs from snapshotPriceCents", () => {
    expect(hasPriceChanged(makeLine({ snapshotPriceCents: 1000, currentPriceCents: 1200 }))).toBe(true);
  });
});

describe("canAddStlGivenOwnership", () => {
  it("is true when the product id is not in the owned set", () => {
    expect(canAddStlGivenOwnership("prod-1", new Set(["prod-2"]))).toBe(true);
  });

  it("is false when the product id is already in the owned set", () => {
    expect(canAddStlGivenOwnership("prod-1", new Set(["prod-1", "prod-2"]))).toBe(false);
  });

  it("is true for an empty owned set", () => {
    expect(canAddStlGivenOwnership("prod-1", new Set())).toBe(true);
  });
});
