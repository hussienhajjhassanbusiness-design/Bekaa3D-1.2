import { canAdjustQuantity } from "./cartInvariants";
import type { CartModel } from "./cartModel";

export interface CartOptimisticState {
  cart: CartModel;
  pendingLineId: string | null;
}

// Pure, contract-independent optimistic-state helper — mirrors
// FVS-023's addressDefaultOptimistic.ts precedent exactly. No
// endpoint, request body, or status code is invented here
// (FVS-025-IMPLEMENTATION-PLAN.md §5).

// Begin an optimistic quantity change for a physical line. A no-op for
// an STL line — quantity is structurally fixed at 1 (mirrors
// `canAdjustQuantity`), so this never silently "succeeds" with a
// wrong quantity.
export function beginQuantityChange(current: CartModel, lineId: string, nextQuantity: number): CartOptimisticState {
  const line = current.lines.find((l) => l.id === lineId);
  if (!line || !canAdjustQuantity(line)) {
    return { cart: current, pendingLineId: null };
  }

  return {
    cart: { ...current, lines: current.lines.map((l) => (l.id === lineId ? { ...l, quantity: nextQuantity } : l)) },
    pendingLineId: lineId,
  };
}

// Begin an optimistic removal.
export function beginRemoval(current: CartModel, lineId: string): CartOptimisticState {
  return {
    cart: { ...current, lines: current.lines.filter((l) => l.id !== lineId) },
    pendingLineId: lineId,
  };
}

// The request failed: restore the exact pre-optimistic snapshot.
export function rollback(previousSnapshot: CartModel): CartOptimisticState {
  return { cart: previousSnapshot, pendingLineId: null };
}

// The request settled successfully: adopt whatever the server
// actually returned, verbatim — never the local optimistic guess.
export function settle(authoritative: CartModel): CartOptimisticState {
  return { cart: authoritative, pendingLineId: null };
}
