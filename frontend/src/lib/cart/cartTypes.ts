import type { PriceRead, ProductType, PublicImage } from "@/lib/catalog/productTypes";

// #ARCHITECTURE-CART-WIRE-CONTRACT
//
// Raw wire shapes, transcribed field for field from the running backend
// 2dfb27b (`GET /openapi.json` components.schemas CartRead, CartLineRead,
// CartItemAdd, CartItemQuantityUpdate, PurchaseRefusal; backend
// docs/cart.md). snake_case on purpose: only cartModel.ts adapts these.
//
// What the contract deliberately does NOT have, so neither does this file:
// a line id (lines are addressed by product_id), a cart total or subtotal,
// a line total, shipping, tax, discount, or a stock count. `snapshot_price`
// is display-only; checkout charges the live price.

// Why a product cannot go in a cart now (VS-022). The same three values
// are the `reason` extension of a 422 PRODUCT_NOT_PURCHASABLE.
export type PurchaseRefusal = "not_listed" | "unavailable" | "whatsapp_only";

export interface CartLineReadDTO {
  product_id: string;
  product_type: ProductType;
  // Null only if the product row is gone (never in V1).
  name: string | null;
  // slug / cover_image / current_price are null once the product is no
  // longer listed (deleted, hidden, category off).
  slug: string | null;
  cover_image: PublicImage | null;
  quantity: number;
  snapshot_price: PriceRead;
  current_price: PriceRead | null;
  price_changed: boolean;
  // The product's current per-line cap; null for STL and unlisted lines.
  max_quantity: number | null;
  // Quantity above the current cap (an admin lowered it); checkout refuses it.
  over_cap: boolean;
  purchasable: boolean;
  unpurchasable_reason: PurchaseRefusal | null;
}

export interface CartReadDTO {
  // Null until the customer's first cart write; GET never creates a cart.
  id: string | null;
  // In the order the lines were first added.
  items: CartLineReadDTO[];
  contains_physical: boolean;
  contains_digital: boolean;
  updated_at: string | null;
}

// `additionalProperties: false`; quantity is a JSON integer >= 1
// (default 1). STL must be 1; a physical merge must stay within the cap.
export interface CartItemAddDTO {
  product_id: string;
  quantity: number;
}
