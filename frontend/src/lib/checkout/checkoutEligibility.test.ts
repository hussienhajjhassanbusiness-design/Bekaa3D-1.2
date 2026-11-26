import { describe, expect, it } from "vitest";
import type { CartLineModel, CartModel } from "@/lib/cart/cartModel";
import type { PublicSettingsModel } from "@/lib/settings/publicSettingsModel";
import { cashOption, checkoutGate, pickupOption } from "./checkoutEligibility";

// Presentation gating only (ADR-024; backend 2dfb27b domain/cash.py,
// domain/fulfillment.py). The server re-decides all of it at checkout.

const SETTINGS: PublicSettingsModel = {
  acceptingOrders: true,
  cashPaymentEnabled: true,
  cashMaxOrderTotal: { amountCents: 10000, currency: "USD" },
  pickupAddress: "Bekaa3D workshop, Zahle",
  pickupHours: "Mon-Fri 10:00-18:00",
  whatsappNumber: null,
};

function line(overrides: Partial<CartLineModel> = {}): CartLineModel {
  return {
    productId: "p-1",
    productType: "physical",
    name: "Dragon",
    slug: "dragon",
    coverImage: null,
    quantity: 1,
    snapshotPrice: { amountCents: 1800, currency: "USD" },
    currentPrice: { amountCents: 1800, currency: "USD" },
    priceChanged: false,
    maxQuantity: 3,
    overCap: false,
    purchasable: true,
    unpurchasableReason: null,
    ...overrides,
  };
}

function cart(lines: CartLineModel[]): CartModel {
  return {
    id: "c",
    lines,
    containsPhysical: lines.some((l) => l.productType === "physical"),
    containsDigital: lines.some((l) => l.productType === "stl"),
    updatedAt: null,
  };
}

describe("cashOption", () => {
  it("offered and eligible for a physical-only cart when cash is enabled, with the public max total", () => {
    expect(cashOption(cart([line()]), SETTINGS)).toEqual({
      offered: true,
      eligible: true,
      maxTotal: { amountCents: 10000, currency: "USD" },
    });
  });

  it("offered but not eligible when any line is an STL (cash needs every line physical)", () => {
    expect(cashOption(cart([line(), line({ productId: "s", productType: "stl" })]), SETTINGS).eligible).toBe(false);
    expect(cashOption(cart([line({ productType: "stl" })]), SETTINGS).eligible).toBe(false);
  });

  it("not offered when cash is disabled or the settings are unknown", () => {
    expect(cashOption(cart([line()]), { ...SETTINGS, cashPaymentEnabled: false })).toMatchObject({
      offered: false,
      eligible: false,
    });
    expect(cashOption(cart([line()]), undefined)).toEqual({
      offered: false,
      eligible: false,
      maxTotal: null,
    });
  });
});

describe("pickupOption", () => {
  it("available only when a pickup address is configured", () => {
    expect(pickupOption(SETTINGS)).toEqual({
      available: true,
      address: SETTINGS.pickupAddress,
      hours: SETTINGS.pickupHours,
    });
    expect(pickupOption({ ...SETTINGS, pickupAddress: null })).toEqual({
      available: false,
      address: null,
      hours: SETTINGS.pickupHours,
    });
    expect(pickupOption(undefined)).toEqual({
      available: false,
      address: null,
      hours: null,
    });
  });
});

describe("checkoutGate", () => {
  const verified = { emailVerified: true };

  it("ready for a clean cart, a verified user and accepting orders", () => {
    expect(
      checkoutGate({
        user: verified,
        cart: cart([line()]),
        settings: SETTINGS,
      })
    ).toEqual({ kind: "ready" });
  });

  it("an unverified account gets verification guidance before anything else", () => {
    expect(
      checkoutGate({
        user: { emailVerified: false },
        cart: cart([line()]),
        settings: SETTINGS,
      })
    ).toEqual({ kind: "verify-email" });
  });

  it("an empty cart cannot proceed", () => {
    expect(checkoutGate({ user: verified, cart: cart([]), settings: SETTINGS })).toEqual({ kind: "empty" });
  });

  it("unpurchasable / over-cap lines block, and are named", () => {
    const gate = checkoutGate({
      user: verified,
      cart: cart([line(), line({ productId: "p-2", overCap: true })]),
      settings: SETTINGS,
    });
    expect(gate.kind).toBe("needs-attention");
    expect(gate.kind === "needs-attention" && gate.lines.map((l) => l.productId)).toEqual(["p-2"]);
  });

  it("a price change alone does not block", () => {
    expect(
      checkoutGate({
        user: verified,
        cart: cart([line({ priceChanged: true })]),
        settings: SETTINGS,
      }).kind
    ).toBe("ready");
  });

  it("paused when the shop is not accepting orders; unknown settings do not block (the server decides)", () => {
    expect(
      checkoutGate({
        user: verified,
        cart: cart([line()]),
        settings: { ...SETTINGS, acceptingOrders: false },
      })
    ).toEqual({ kind: "paused" });
    expect(
      checkoutGate({
        user: verified,
        cart: cart([line()]),
        settings: undefined,
      })
    ).toEqual({ kind: "ready" });
  });
});
