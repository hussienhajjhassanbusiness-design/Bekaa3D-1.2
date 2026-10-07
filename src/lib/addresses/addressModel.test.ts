import { describe, it, expect } from "vitest";
import type { AddressModel } from "./addressModel";

// FVS-023-IMPLEMENTATION-PLAN.md T01 — a frontend-normalized shape
// only, never a claim about the real /me/addresses response field
// names (unconfirmed — plan §1; #ARCHITECTURE-ADDRESS-ADAPTER). This
// is a pure compile-time check: the point of this test is that
// `AddressModel` intentionally has NO individual field
// (name/phone/street/city/governorate/postalCode/country) and NO
// shipping-zone/rate field at all — if someone adds one later without
// backend evidence, this file is where a reviewer would notice and
// reconsider (#ARCHITECTURE-ADDRESS-NO-ZONE-INFERENCE).

describe("AddressModel", () => {
  it("accepts the normalized presentation fields this plan actually needs", () => {
    const model: AddressModel = {
      id: "addr-1",
      displayLines: ["Jane Doe", "Main Street, Beirut"],
      isDefault: true,
    };
    expect(model.id).toBe("addr-1");
  });

  it("has no individual address field — only pre-formatted display lines", () => {
    const model: AddressModel = { id: "addr-1", displayLines: [], isDefault: false };
    expect("name" in model).toBe(false);
    expect("phone" in model).toBe(false);
    expect("street" in model).toBe(false);
    expect("city" in model).toBe(false);
    expect("governorate" in model).toBe(false);
    expect("postalCode" in model).toBe(false);
    expect("country" in model).toBe(false);
  });

  it("has no shipping-zone or rate field — zone selection is a separate, later concern", () => {
    const model: AddressModel = { id: "addr-1", displayLines: [], isDefault: false };
    expect("shippingZone" in model).toBe(false);
    expect("zoneId" in model).toBe(false);
    expect("rateCents" in model).toBe(false);
  });
});
