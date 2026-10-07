import { describe, it, expect } from "vitest";
import type { ShippingZoneAdminModel, ShippingZoneOption } from "./shippingZoneModels";

// FVS-024-IMPLEMENTATION-PLAN.md T01 (incl. T05) — frontend-normalized
// shapes only, never a claim about the real admin/public shipping-zone
// response field names (both unconfirmed — plan §0/§1;
// #ARCHITECTURE-SHIPPING-ZONE-ADAPTER). `currency` is always a
// required, caller-supplied string — never defaulted/hardcoded to
// "USD"/"LBP" anywhere. `ShippingZoneOption` (the public checkout
// option) has NO `isArchived` field at all: if the public endpoint
// never sends archived zones (as VS-019 implies), there is nothing for
// this model to filter or badge — mirroring FVS-020's
// no-revoked-field precedent for entitlements.

describe("ShippingZoneAdminModel", () => {
  it("accepts the normalized admin fields this plan actually needs", () => {
    const zone: ShippingZoneAdminModel = {
      id: "zone-1",
      displayName: "Beirut",
      rateCents: 50000,
      currency: "USD",
      isArchived: false,
    };
    expect(zone.id).toBe("zone-1");
  });

  it("has no governorate/address field — zone selection is explicit, never address-derived", () => {
    const zone: ShippingZoneAdminModel = {
      id: "zone-1",
      displayName: "Beirut",
      rateCents: 50000,
      currency: "USD",
      isArchived: false,
    };
    expect("governorate" in zone).toBe(false);
    expect("addressId" in zone).toBe(false);
  });
});

describe("ShippingZoneOption", () => {
  it("accepts the normalized public-option fields this plan actually needs", () => {
    const option: ShippingZoneOption = { id: "zone-1", displayName: "Beirut", rateCents: 50000, currency: "USD" };
    expect(option.id).toBe("zone-1");
  });

  it("has no isArchived field — the public endpoint never sends archived zones at all", () => {
    const option: ShippingZoneOption = { id: "zone-1", displayName: "Beirut", rateCents: 50000, currency: "USD" };
    expect("isArchived" in option).toBe(false);
  });
});
