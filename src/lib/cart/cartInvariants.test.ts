import { describe, it, expect } from "vitest";
import { canChangeQuantity, cartNeedsAttention, quantityControl } from "./cartInvariants";
import type { CartLineModel, CartModel } from "./cartModel";

// UX helpers only. The server still refuses an STL quantity above 1, a
// quantity above the current cap, and any PATCH on an unpurchasable line.

function line(overrides: Partial<CartLineModel> = {}): CartLineModel {
  return {
    productId: "p-1",
    productType: "physical",
    name: "Dragon",
    slug: "dragon",
    coverImage: null,
    quantity: 2,
    snapshotPrice: { amountCents: 2500, currency: "USD" },
    currentPrice: { amountCents: 2500, currency: "USD" },
    priceChanged: false,
    maxQuantity: 5,
    overCap: false,
    purchasable: true,
    unpurchasableReason: null,
    ...overrides,
  };
}

describe("canChangeQuantity", () => {
  it("allows a purchasable physical line", () => {
    expect(canChangeQuantity(line())).toBe(true);
  });

  it("never allows an STL line: its quantity is always 1", () => {
    expect(canChangeQuantity(line({ productType: "stl", quantity: 1, maxQuantity: null }))).toBe(false);
  });

  it("never allows an unpurchasable line: the backend refuses PATCH on it", () => {
    expect(canChangeQuantity(line({ purchasable: false, unpurchasableReason: "unavailable" }))).toBe(false);
  });
});

describe("quantityControl", () => {
  it("can decrease above 1 and increase below the server's max_quantity", () => {
    expect(quantityControl(line({ quantity: 2, maxQuantity: 5 }))).toEqual({
      canDecrease: true,
      canIncrease: true,
      reduceToCap: null,
    });
  });

  it("cannot decrease below 1 (Remove is the action for that)", () => {
    expect(quantityControl(line({ quantity: 1 })).canDecrease).toBe(false);
  });

  it("cannot increase at the cap", () => {
    expect(quantityControl(line({ quantity: 5, maxQuantity: 5 })).canIncrease).toBe(false);
  });

  it("does not invent a cap when max_quantity is null", () => {
    expect(quantityControl(line({ quantity: 40, maxQuantity: null })).canIncrease).toBe(true);
  });

  it("offers reduce-to-cap and no increase for a line the server marks over_cap", () => {
    expect(quantityControl(line({ quantity: 8, maxQuantity: 3, overCap: true }))).toEqual({
      canDecrease: true,
      canIncrease: false,
      reduceToCap: 3,
    });
  });

  it("offers nothing on an STL line", () => {
    expect(quantityControl(line({ productType: "stl", quantity: 1, maxQuantity: null }))).toEqual({
      canDecrease: false,
      canIncrease: false,
      reduceToCap: null,
    });
  });
});

describe("cartNeedsAttention", () => {
  const cart = (lines: CartLineModel[]): CartModel => ({
    id: "c",
    lines,
    containsPhysical: true,
    containsDigital: false,
    updatedAt: null,
  });

  it("is false when every line is purchasable, within cap, and unchanged in price", () => {
    expect(cartNeedsAttention(cart([line()]))).toBe(false);
  });

  it.each([
    ["unpurchasable", { purchasable: false, unpurchasableReason: "unavailable" as const }],
    ["over the cap", { overCap: true }],
    ["price changed", { priceChanged: true }],
  ])("is true when a line is %s", (_label, overrides) => {
    expect(cartNeedsAttention(cart([line(), line({ productId: "p-2", ...overrides })]))).toBe(true);
  });
});
