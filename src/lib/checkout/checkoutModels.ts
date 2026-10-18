// #ARCHITECTURE-CHECKOUT-ADAPTER
//
// Frontend-normalized shapes only — never a claim about the real
// POST /checkout request field names, which are unconfirmed
// (FVS-026-IMPLEMENTATION-PLAN.md §0/§1).

// Order-level only — per-line delivery granularity for a mixed cart
// is explicitly unresolved by every source audited (plan §0); this
// type does not guess it. No `zoneId`/shipping-cost field anywhere:
// ADR-024 removed shipping charges entirely, so choosing an address
// is itself a complete selection — there is no further delivery-cost
// step to resolve.
export type DeliveryMethodSelection = { kind: "address"; addressId: string } | { kind: "pickup" };

export interface ConsentState {
  termsAccepted: boolean;
  digitalConsentByProductId: Readonly<Record<string, boolean>>;
}

// A price-change conflict line. No backend status/RFC-code field is
// claimed here — that mapping belongs to a future adapter once the
// conflict payload shape is confirmed.
export interface PriceConflictLine {
  lineId: string;
  productDisplayName: string;
  oldPriceCents: number;
  newPriceCents: number;
  currency: string;
}

// `kind` is a frontend-owned presentation category, never a claimed
// backend code — the exact cart-concurrency representation is
// unconfirmed (plan §0/§4). `message` is always caller-supplied text
// from a future adapter, never fabricated here.
export type CartConflictKind = "unavailable" | "quantity-adjusted" | "removed";

export interface CartConflictLine {
  lineId: string;
  kind: CartConflictKind;
  message: string;
}
