import { describe, it, expect } from "vitest";
import { adaptCart, adaptCartLine, cartItemCount } from "./cartModel";
import type { CartLineReadDTO, CartReadDTO } from "./cartTypes";

// Phase 5C (FVS-025) — CartRead / CartLineRead exactly as the running
// backend 2dfb27b serves them (openapi.json components.schemas.CartRead,
// CartLineRead; docs/cart.md in the backend repo).

const PHYSICAL: CartLineReadDTO = {
  product_id: "p-1",
  product_type: "physical",
  name: "Dragon",
  slug: "dragon",
  cover_image: { id: "img-1", url: "http://localhost:8001/products/dragon.webp", alt_text: "A dragon", is_cover: true },
  quantity: 2,
  snapshot_price: { amount_cents: 2500, currency: "USD" },
  current_price: { amount_cents: 2500, currency: "USD" },
  price_changed: false,
  max_quantity: 5,
  over_cap: false,
  purchasable: true,
  unpurchasable_reason: null,
};

const STL: CartLineReadDTO = {
  product_id: "p-2",
  product_type: "stl",
  name: "Dragon STL",
  slug: "dragon-stl",
  cover_image: null,
  quantity: 1,
  snapshot_price: { amount_cents: 900, currency: "USD" },
  current_price: { amount_cents: 1200, currency: "USD" },
  price_changed: true,
  max_quantity: null,
  over_cap: false,
  purchasable: true,
  unpurchasable_reason: null,
};

const CART: CartReadDTO = {
  id: "cart-1",
  items: [PHYSICAL, STL],
  contains_physical: true,
  contains_digital: true,
  updated_at: "2026-11-11T10:00:00Z",
};

describe("adaptCartLine", () => {
  it("maps every CartLineRead field, addressed by product_id (there is no line id)", () => {
    expect(adaptCartLine(PHYSICAL)).toEqual({
      productId: "p-1",
      productType: "physical",
      name: "Dragon",
      slug: "dragon",
      coverImage: { src: "http://localhost:8001/products/dragon.webp", alt: "A dragon" },
      quantity: 2,
      snapshotPrice: { amountCents: 2500, currency: "USD" },
      currentPrice: { amountCents: 2500, currency: "USD" },
      priceChanged: false,
      maxQuantity: 5,
      overCap: false,
      purchasable: true,
      unpurchasableReason: null,
    });
  });

  it("keeps the server's price_changed flag rather than recomputing it", () => {
    const line = adaptCartLine({ ...STL, price_changed: false });
    expect(line.priceChanged).toBe(false);
    expect(line.currentPrice).toEqual({ amountCents: 1200, currency: "USD" });
  });

  it("falls back to the product name for a cover image without alt text", () => {
    const line = adaptCartLine({ ...PHYSICAL, cover_image: { ...PHYSICAL.cover_image!, alt_text: null } });
    expect(line.coverImage).toEqual({ src: PHYSICAL.cover_image!.url, alt: "Dragon" });
  });

  it("preserves null slug/cover/current price/max quantity and the refusal reason of an unlisted line", () => {
    const line = adaptCartLine({
      ...PHYSICAL,
      name: null,
      slug: null,
      cover_image: null,
      current_price: null,
      max_quantity: null,
      purchasable: false,
      unpurchasable_reason: "not_listed",
    });
    expect(line).toMatchObject({
      name: null,
      slug: null,
      coverImage: null,
      currentPrice: null,
      maxQuantity: null,
      purchasable: false,
      unpurchasableReason: "not_listed",
    });
  });
});

describe("adaptCart", () => {
  it("maps CartRead and keeps the server's line order", () => {
    const cart = adaptCart(CART);
    expect(cart.id).toBe("cart-1");
    expect(cart.lines.map((line) => line.productId)).toEqual(["p-1", "p-2"]);
    expect(cart.containsPhysical).toBe(true);
    expect(cart.containsDigital).toBe(true);
    expect(cart.updatedAt).toBe("2026-11-11T10:00:00Z");
  });

  it("accepts a never-written cart (id null, no items)", () => {
    const cart = adaptCart({ id: null, items: [], contains_physical: false, contains_digital: false, updated_at: null });
    expect(cart).toEqual({ id: null, lines: [], containsPhysical: false, containsDigital: false, updatedAt: null });
  });

  it("has no total or subtotal field: CartRead has none and checkout charges live prices", () => {
    const cart = adaptCart(CART) as unknown as Record<string, unknown>;
    expect(Object.keys(cart).sort()).toEqual(["containsDigital", "containsPhysical", "id", "lines", "updatedAt"]);
  });
});

describe("cartItemCount", () => {
  it("sums line quantities (a count, never a price)", () => {
    expect(cartItemCount(adaptCart(CART))).toBe(3);
  });

  it("is 0 for an empty cart", () => {
    expect(cartItemCount(adaptCart({ ...CART, items: [] }))).toBe(0);
  });
});
