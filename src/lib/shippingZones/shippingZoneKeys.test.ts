import { describe, it, expect } from "vitest";
import { shippingZoneKeys } from "./shippingZoneKeys";

// FVS-024-IMPLEMENTATION-PLAN.md T01 — the ONE canonical shipping-zone
// query-key family (#ARCHITECTURE-CANONICAL-SHIPPING-ZONES). One
// shared root distinguishes the admin and public reads of the same
// underlying resource — FVS-024's admin management and FVS-026's
// future checkout zone-picker must share this root rather than each
// inventing an unrelated cache for the same concept.

describe("shippingZoneKeys", () => {
  it("has a stable root key", () => {
    expect(shippingZoneKeys.root).toEqual(["shippingZones"]);
  });

  it("derives the admin-list key from the canonical root", () => {
    expect(shippingZoneKeys.adminList()).toEqual(["shippingZones", "adminList"]);
  });

  it("derives the public-list key from the canonical root", () => {
    expect(shippingZoneKeys.publicList()).toEqual(["shippingZones", "publicList"]);
  });

  it("keeps admin and public list keys distinguishable from each other and from the bare root", () => {
    const admin = shippingZoneKeys.adminList();
    const pub = shippingZoneKeys.publicList();
    const root = shippingZoneKeys.root;
    expect(admin).not.toEqual(pub);
    expect(admin).not.toEqual(root);
    expect(pub).not.toEqual(root);
  });

  it("takes no filter/page argument for either list — pagination/filter contract is unconfirmed", () => {
    // @ts-expect-error — adminList() intentionally accepts no arguments
    expect(() => shippingZoneKeys.adminList(1)).not.toThrow();
    // @ts-expect-error — publicList() intentionally accepts no arguments
    expect(() => shippingZoneKeys.publicList(1)).not.toThrow();
  });
});
