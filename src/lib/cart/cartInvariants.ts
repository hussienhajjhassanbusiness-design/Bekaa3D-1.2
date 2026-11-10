import type { CartLineModel, CartModel } from "./cartModel";

// #SECURITY-CART-SERVER-AUTHORITY
//
// UX helpers only, never a security boundary. The backend refuses an STL
// quantity other than 1, a quantity above the current cap, and any PATCH
// on an unpurchasable line, whatever these functions say.

// STL lines are always quantity 1 (DB CHECK + 422 QUANTITY_EXCEEDS_LIMIT
// with max_quantity 1). Unpurchasable lines refuse PATCH; DELETE still works.
export function canChangeQuantity(line: CartLineModel): boolean {
  return line.productType === "physical" && line.purchasable;
}

export interface QuantityControlState {
  canDecrease: boolean;
  canIncrease: boolean;
  // The server's current cap when the line is over it (over_cap), so the
  // UI can offer one action that brings it back within the cap.
  reduceToCap: number | null;
}

export function quantityControl(line: CartLineModel): QuantityControlState {
  if (!canChangeQuantity(line)) {
    return { canDecrease: false, canIncrease: false, reduceToCap: null };
  }
  const cap = line.maxQuantity;
  const reduceToCap = line.overCap && cap !== null && cap >= 1 ? cap : null;
  return {
    canDecrease: line.quantity > 1,
    canIncrease: !line.overCap && (cap === null || line.quantity < cap),
    reduceToCap,
  };
}

// True when checkout would refuse something as the cart stands: an
// unpurchasable line, an over-cap line, or an unconfirmed price change
// (VS-023 409 CART_PRICE_CHANGED). Display guidance only.
export function cartNeedsAttention(cart: CartModel): boolean {
  return cart.lines.some((line) => !line.purchasable || line.overCap || line.priceChanged);
}
