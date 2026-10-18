import type { CartLineModel } from "./cartModel";

// #SECURITY-CART-SERVER-AUTHORITY
//
// Every helper in this file is a pure UX nicety only — never a
// security boundary. A stale or incomplete client cache must never be
// treated as authorization; the server remains the final, sole
// authority for cart contents/price/availability/quantity regardless
// of what these functions return (FVS-025-IMPLEMENTATION-PLAN.md §0).

export function isStlLine(line: CartLineModel): boolean {
  return line.productType === "stl";
}

// STL quantity is always fixed at 1 — no stepper is ever rendered for
// an STL line, enforced structurally here rather than per-component.
export function canAdjustQuantity(line: CartLineModel): boolean {
  return line.productType === "physical";
}

export function hasPriceChanged(line: CartLineModel): boolean {
  return line.currentPriceCents !== undefined && line.currentPriceCents !== line.snapshotPriceCents;
}
