// #ARCHITECTURE-REFUND-LINE-CEILINGS
//
// `refundableBalanceCents` is always SERVER-supplied — never derived
// from purchase price, current price, line total, or any
// already-refunded arithmetic (#SECURITY-SERVER-REFUND-BALANCE-AUTHORITY).
// `isDigital` is optional and presentation-only; it only ever
// triggers an informational warning, never an authorization decision
// or a confirmation gate — ADR-019 means there is no entitlement to
// revoke, so a digital line simply becomes refunded like any other.
//
// No shipping candidate exists here: ADR-024 means nothing was ever
// charged for shipping, so there is nothing to refund.
export interface RefundLineCandidate {
  lineId: string;
  productDisplayName: string;
  refundableBalanceCents: number;
  currency: string;
  isDigital?: boolean;
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
