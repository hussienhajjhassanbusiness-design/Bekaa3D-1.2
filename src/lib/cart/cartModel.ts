// #ARCHITECTURE-CART-ADAPTER
//
// Frontend-normalized shapes only — never a claim about the real
// `GET /api/v1/cart` response field names, which are unconfirmed
// (FVS-025-IMPLEMENTATION-PLAN.md §0/§1). Holds only the concepts
// VS-020/FVS-025 actually confirm: merge-on-duplicate-add, STL qty
// locked to 1, server-owned max quantity, and price snapshot vs.
// current price.
//
// Deliberately has NO availability/unavailable field — whether the
// backend flags an unavailable line in place or removes it entirely
// with a separate signal is unconfirmed (plan §0/§4 Q14/Q35/Q36); a
// future adapter/UI layer decides how to surface that once it is.
export interface CartLineModel {
  id: string;
  productId: string;
  productDisplayName: string;
  productType: "physical" | "stl";
  quantity: number;
  maxQuantity?: number;
  snapshotPriceCents: number;
  currentPriceCents?: number;
  currency: string;
  thumbnailSrc?: string;
}

// Deliberately has NO totals/subtotal field — no source confirms
// GET /cart returns one; totals computation belongs to checkout
// (VS-021), not cart read (plan §0/§1).
export interface CartModel {
  id: string;
  lines: readonly CartLineModel[];
}
