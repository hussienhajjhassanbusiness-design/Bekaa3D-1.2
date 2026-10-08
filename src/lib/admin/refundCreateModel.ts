// #ARCHITECTURE-REFUND-LINE-CEILINGS
//
// `refundableBalanceCents` is always SERVER-supplied — never derived
// from purchase price, current price, line total, or any
// already-refunded arithmetic (#SECURITY-SERVER-REFUND-BALANCE-AUTHORITY).
// `isDigital` is optional and presentation-only; it only ever
// triggers an extra confirmation step, never an authorization
// decision.
export interface RefundLineCandidate {
  lineId: string;
  productDisplayName: string;
  refundableBalanceCents: number;
  currency: string;
  isDigital?: boolean;
}

export interface ShippingRefundCandidate {
  refundableBalanceCents: number;
  currency: string;
}

export type RefundLineAmountValidation =
  | { ok: true }
  | { ok: false; reason: "exceeds-ceiling" | "negative" };

// #SECURITY-REFUND-RACE-SERVER-WINS
//
// A pure UX-only precheck against the server-supplied ceiling — never
// authoritative. It never clamps the input and never computes a
// replacement value; a race where another admin refunds first is
// only ever caught by the server rejecting the real request, which
// this function cannot see or predict.
export function validateRefundLineAmount(amountCents: number | null, ceilingCents: number): RefundLineAmountValidation {
  if (amountCents === null) {
    return { ok: true };
  }
  if (amountCents < 0) {
    return { ok: false, reason: "negative" };
  }
  if (amountCents > ceilingCents) {
    return { ok: false, reason: "exceeds-ceiling" };
  }
  return { ok: true };
}
