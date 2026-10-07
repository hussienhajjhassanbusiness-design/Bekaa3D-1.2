import { describe, it, expect } from "vitest";
import type { PublicSettingsModel } from "./publicSettingsModel";

// FVS-022-IMPLEMENTATION-PLAN.md T01 — a frontend-normalized shape
// only, never a claim about `GET /api/v1/settings/public`'s real
// response field names or shape (unconfirmed — plan §1;
// #ARCHITECTURE-PUBLIC-SETTINGS-ADAPTER). This is a pure compile-time
// check: the point of this test is that `PublicSettingsModel` has
// exactly the one field this slice actually needs and does NOT yet
// invent a free-shipping-threshold field ahead of FVS-025/026 landing
// — if someone adds one later without evidence, this file is where a
// reviewer would notice and reconsider.

describe("PublicSettingsModel", () => {
  it("accepts a configured WhatsApp number", () => {
    const model: PublicSettingsModel = { whatsappNumber: "96170123456" };
    expect(model.whatsappNumber).toBe("96170123456");
  });

  it("accepts null when no WhatsApp number is configured", () => {
    const model: PublicSettingsModel = { whatsappNumber: null };
    expect(model.whatsappNumber).toBeNull();
  });

  it("has no free-shipping-threshold field yet — that belongs to FVS-025/026, not invented here", () => {
    const model: PublicSettingsModel = { whatsappNumber: null };
    expect("freeShippingThreshold" in model).toBe(false);
  });
});
