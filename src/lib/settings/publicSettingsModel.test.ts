import { describe, it, expect } from "vitest";
import { toPublicSettingsModel, type PublicSettingsRead } from "./publicSettingsModel";

// Current backend contract: docs/backend-handoff/openapi.json
// `PublicSettingsRead` at backend commit 2dfb27b. Exactly six required
// keys; `free_shipping_threshold` was removed by VS-028 (ADR-024);
// `cash_max_order_total` is a required, non-nullable MoneyRead. The three
// text fields are nullable ("not configured" -> the UI hides the element).

function rawSettings(overrides: Partial<PublicSettingsRead> = {}): PublicSettingsRead {
  return {
    accepting_orders: true,
    cash_payment_enabled: true,
    cash_max_order_total: { amount_cents: 10000, currency: "USD" },
    pickup_address: null,
    pickup_hours: null,
    whatsapp_number: null,
    ...overrides,
  };
}

describe("PublicSettingsRead (wire type, current contract)", () => {
  it("has exactly the six current keys and no free_shipping_threshold", () => {
    const raw = rawSettings();
    expect(Object.keys(raw).sort()).toEqual([
      "accepting_orders",
      "cash_max_order_total",
      "cash_payment_enabled",
      "pickup_address",
      "pickup_hours",
      "whatsapp_number",
    ]);
    expect("free_shipping_threshold" in raw).toBe(false);
  });

  it("rejects free_shipping_threshold at compile time", () => {
    // @ts-expect-error free_shipping_threshold was removed by VS-028 (ADR-024)
    const raw: PublicSettingsRead = { ...rawSettings(), free_shipping_threshold: null };
    expect(raw).toBeDefined();
  });

  it("requires cash_max_order_total to be non-null MoneyRead at compile time", () => {
    // @ts-expect-error cash_max_order_total is required and not nullable
    const raw: PublicSettingsRead = { ...rawSettings(), cash_max_order_total: null };
    expect(raw).toBeDefined();
  });
});

describe("toPublicSettingsModel", () => {
  it("maps every current field", () => {
    const model = toPublicSettingsModel(
      rawSettings({
        accepting_orders: false,
        cash_payment_enabled: false,
        cash_max_order_total: { amount_cents: 25000, currency: "USD" },
        pickup_address: "Zahle, main street",
        pickup_hours: "Mon-Fri 9-5",
        whatsapp_number: "+96170000000",
      })
    );
    expect(model).toEqual({
      acceptingOrders: false,
      cashPaymentEnabled: false,
      cashMaxOrderTotal: { amountCents: 25000, currency: "USD" },
      pickupAddress: "Zahle, main street",
      pickupHours: "Mon-Fri 9-5",
      whatsappNumber: "96170000000",
    });
  });

  it("surfaces cash_payment_enabled true", () => {
    expect(toPublicSettingsModel(rawSettings({ cash_payment_enabled: true })).cashPaymentEnabled).toBe(true);
  });

  it("surfaces cash_max_order_total as integer cents, never a float", () => {
    const model = toPublicSettingsModel(rawSettings({ cash_max_order_total: { amount_cents: 10000, currency: "USD" } }));
    expect(model.cashMaxOrderTotal).toEqual({ amountCents: 10000, currency: "USD" });
  });

  it("never exposes a free-shipping-threshold field", () => {
    const model = toPublicSettingsModel(rawSettings());
    expect("freeShippingThreshold" in model).toBe(false);
    expect("free_shipping_threshold" in model).toBe(false);
  });

  it("keeps unconfigured text fields null", () => {
    const model = toPublicSettingsModel(rawSettings());
    expect(model.pickupAddress).toBeNull();
    expect(model.pickupHours).toBeNull();
    expect(model.whatsappNumber).toBeNull();
  });

  it("strips the leading '+' and any formatting from an E.164 WhatsApp number", () => {
    expect(toPublicSettingsModel(rawSettings({ whatsapp_number: "+96170000000" })).whatsappNumber).toBe("96170000000");
    expect(toPublicSettingsModel(rawSettings({ whatsapp_number: "+961 70-000-000" })).whatsappNumber).toBe("96170000000");
  });

  it("maps a null whatsapp_number to null — never a fallback number", () => {
    expect(toPublicSettingsModel(rawSettings({ whatsapp_number: null })).whatsappNumber).toBeNull();
  });
});
