import { describe, it, expect } from "vitest";
import { canChangeQuantity, cartBlockingLines, cartNeedsAttention, quantityControl } from "./cartInvariants";
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

// Phase 5D — what blocks checkout as the cart stands. A price change does
// NOT block: checkout itself answers 409 CART_PRICE_CHANGED and asks the
// customer to accept the new price explicitly.
describe("cartBlockingLines", () => {
  const cart = (lines: CartLineModel[]): CartModel => ({
    id: "c",
    lines,
    containsPhysical: true,
    containsDigital: false,
    updatedAt: null,
  });

  it("lists unpurchasable and over-cap lines only", () => {
    const blocked = cartBlockingLines(
      cart([
        line(),
        line({
          productId: "p-2",
          purchasable: false,
          unpurchasableReason: "whatsapp_only",
        }),
        line({ productId: "p-3", overCap: true }),
        line({ productId: "p-4", priceChanged: true }),
      ])
    );
    expect(blocked.map((l) => l.productId)).toEqual(["p-2", "p-3"]);
  });

  it("is empty for a clean cart", () => {
    expect(cartBlockingLines(cart([line(), line({ productId: "p-2", priceChanged: true })]))).toEqual([]);
  });
});
