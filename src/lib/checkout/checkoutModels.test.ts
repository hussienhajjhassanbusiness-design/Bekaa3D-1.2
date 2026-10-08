import { describe, it, expect } from "vitest";
import type { DeliveryMethodSelection, ConsentState, PriceConflictLine, CartConflictLine } from "./checkoutModels";

// FVS-026-IMPLEMENTATION-PLAN.md T02 — frontend-normalized shapes
// only, never a claim about the real POST /checkout request field
// names (unconfirmed — plan §0/§1; #ARCHITECTURE-CHECKOUT-ADAPTER).
// `DeliveryMethodSelection` is order-level only (per-line granularity
// is unresolved, not guessed). `CartConflictLine.kind` is a
// frontend-owned presentation category, never a claimed backend code.

describe("DeliveryMethodSelection", () => {
  it("accepts an address+zone selection", () => {
    const selection: DeliveryMethodSelection = { kind: "address", addressId: "addr-1", zoneId: "zone-1" };
    expect(selection.kind).toBe("address");
  });

  it("accepts a pickup selection with no address/zone fields", () => {
    const selection: DeliveryMethodSelection = { kind: "pickup" };
    expect(selection.kind).toBe("pickup");
  });

  it("has no governorate/address-parsing field on either variant", () => {
    const selection: DeliveryMethodSelection = { kind: "pickup" };
    expect("governorate" in selection).toBe(false);
  });
});

describe("ConsentState", () => {
  it("accepts terms acceptance plus per-product digital consent", () => {
    const state: ConsentState = { termsAccepted: true, digitalConsentByProductId: { "prod-1": true, "prod-2": false } };
    expect(state.termsAccepted).toBe(true);
  });
});

describe("PriceConflictLine", () => {
  it("accepts the normalized fields this plan actually needs", () => {
    const line: PriceConflictLine = {
      lineId: "line-1",
      productDisplayName: "Garden Gnome",
      oldPriceCents: 1000,
      newPriceCents: 1200,
      currency: "USD",
    };
    expect(line.lineId).toBe("line-1");
  });

  it("has no backend status/RFC-code field — this layer never claims one", () => {
    const line: PriceConflictLine = {
      lineId: "line-1",
      productDisplayName: "Garden Gnome",
      oldPriceCents: 1000,
      newPriceCents: 1200,
      currency: "USD",
    };
    expect("httpStatus" in line).toBe(false);
    expect("rfcCode" in line).toBe(false);
  });
});

describe("CartConflictLine", () => {
  it("accepts a frontend-owned conflict kind plus a caller-supplied message", () => {
    const line: CartConflictLine = { lineId: "line-1", kind: "unavailable", message: "This item is no longer available." };
    expect(line.kind).toBe("unavailable");
  });

  it("accepts the quantity-adjusted and removed kinds", () => {
    const a: CartConflictLine = { lineId: "line-1", kind: "quantity-adjusted", message: "Quantity was reduced to 2." };
    const b: CartConflictLine = { lineId: "line-2", kind: "removed", message: "This item was removed from your cart." };
    expect(a.kind).toBe("quantity-adjusted");
    expect(b.kind).toBe("removed");
  });
});
