import { describe, it, expect } from "vitest";
import { toPublicSettingsModel, type PublicSettingsModel, type PublicSettingsRead } from "./publicSettingsModel";

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

function rawSettings(overrides: Partial<PublicSettingsRead> = {}): PublicSettingsRead {
  return {
    accepting_orders: true,
    free_shipping_threshold: null,
    pickup_address: null,
    pickup_hours: null,
    whatsapp_number: null,
    ...overrides,
  };
}

describe("toPublicSettingsModel", () => {
  it("strips the leading '+' and any formatting from an E.164 WhatsApp number (BACKEND-RESPONSE.md B1 example)", () => {
    const model = toPublicSettingsModel(rawSettings({ whatsapp_number: "+96170000000" }));
    expect(model.whatsappNumber).toBe("96170000000");
  });

  it("maps a null whatsapp_number to null — never a fallback number", () => {
    const model = toPublicSettingsModel(rawSettings({ whatsapp_number: null }));
    expect(model.whatsappNumber).toBeNull();
  });

  it("strips spaces/hyphens alongside the leading '+'", () => {
    const model = toPublicSettingsModel(rawSettings({ whatsapp_number: "+961 70-000-000" }));
    expect(model.whatsappNumber).toBe("96170000000");
  });
});
