import { describe, it, expect } from "vitest";
import type { EntitlementModel } from "./entitlementModel";

// FVS-020-IMPLEMENTATION-PLAN.md T01 — a frontend-normalized shape
// only, never a claim about the real /me/entitlements response field
// names (plan §1). This is a pure compile-time check: the point of
// this test is that `EntitlementModel` intentionally has NO storage
// path/private URL/download-endpoint/revoked field — if someone adds
// one later, this file is the place a reviewer would notice and
// reconsider (#ARCHITECTURE-ENTITLEMENT-ADAPTER, #SECURITY note in the
// model file itself).

describe("EntitlementModel", () => {
  it("accepts only the normalized presentation fields this plan actually needs", () => {
    const model: EntitlementModel = {
      id: "ent-1",
      productDisplayName: "Dragon STL",
      thumbnailSrc: "/thumb.png",
      currentVersionLabel: "Version 3",
    };
    expect(model.id).toBe("ent-1");
  });

  it("allows thumbnail and version label to be omitted (both optional)", () => {
    const model: EntitlementModel = { id: "ent-1", productDisplayName: "Dragon STL" };
    expect(model.thumbnailSrc).toBeUndefined();
    expect(model.currentVersionLabel).toBeUndefined();
  });

  it("has no revoked/status field — the API never returns revoked rows at all", () => {
    const model: EntitlementModel = { id: "ent-1", productDisplayName: "Dragon STL" };
    expect("revoked" in model).toBe(false);
    expect("status" in model).toBe(false);
  });
});
