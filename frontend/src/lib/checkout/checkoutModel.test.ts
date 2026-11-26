import { describe, expect, it } from "vitest";
import { adaptCheckoutRead, isFollowableRedirect } from "./checkoutModel";
import type { CheckoutReadDTO } from "./checkoutTypes";

// #ARCHITECTURE-CHECKOUT-RESPONSE-ADAPTER — CheckoutRead (backend 2dfb27b
// checkout_schemas.py). Every figure shown after checkout comes from here.

const usd = (amount_cents: number) => ({ amount_cents, currency: "USD" });

const CASH: CheckoutReadDTO = {
  order: {
    id: "o-1",
    order_number: "B3D-2026-000123",
    source: "cart",
    status: "in_progress",
    payment_method: "cash",
    fulfillment_method: "delivery",
    subtotal: usd(3600),
    tax: usd(0),
    total: usd(3600),
    placed_at: "2026-11-11T10:00:00Z",
    estimated_dispatch_at: "2026-11-14T10:00:00Z",
    delivery_fee_note: "The delivery fee is paid to the courier on delivery.",
    delivery_address: {
      recipient_name: "Ada",
      governorate: "beqaa",
      city: "Zahle",
      area: null,
      street: "Main St",
      landmark_notes: "Blue door",
    },
    payment_due: true,
    amount_due: usd(3600),
    lines: [
      {
        id: "l-1",
        product_id: "p-1",
        product_type: "physical",
        name: "Dragon",
        unit_price: usd(1800),
        quantity: 2,
        line_total: usd(3600),
        fulfillment_status: "pending",
      },
    ],
  },
  payment: null,
  dropped_lines: [],
};

const ONLINE: CheckoutReadDTO = {
  order: {
    ...CASH.order,
    status: "pending_payment",
    payment_method: "online",
    fulfillment_method: null,
    delivery_fee_note: null,
    delivery_address: null,
    payment_due: false,
    amount_due: null,
  },
  payment: {
    id: "pay-1",
    status: "pending",
    provider: "mock",
    redirect_url: "http://localhost:3000/checkout/return?order=B3D-2026-000123",
  },
  dropped_lines: [{ product_id: "p-owned", reason: "already_owned" }],
};

describe("adaptCheckoutRead", () => {
  it("cash: maps order identifiers, server totals, amount due and the delivery snapshot", () => {
    const model = adaptCheckoutRead(CASH);
    expect(model).toMatchObject({
      orderId: "o-1",
      orderNumber: "B3D-2026-000123",
      status: "in_progress",
      paymentMethod: "cash",
      fulfillmentMethod: "delivery",
      subtotal: { amountCents: 3600, currency: "USD" },
      total: { amountCents: 3600, currency: "USD" },
      paymentDue: true,
      amountDue: { amountCents: 3600, currency: "USD" },
      estimatedDispatchAt: "2026-11-14T10:00:00Z",
      payment: null,
      droppedProductIds: [],
      next: "cash-confirmation",
    });
    expect(model.deliveryAddress).toEqual({
      recipientName: "Ada",
      lines: ["Main St", "Zahle, Beqaa", "Blue door"],
    });
    expect(model.lines).toEqual([
      {
        id: "l-1",
        productId: "p-1",
        productType: "physical",
        name: "Dragon",
        unitPrice: { amountCents: 1800, currency: "USD" },
        quantity: 2,
        lineTotal: { amountCents: 3600, currency: "USD" },
        fulfillmentStatus: "pending",
      },
    ]);
  });

  it("online: keeps the payment and its opaque redirect_url, and the dropped product ids", () => {
    const model = adaptCheckoutRead(ONLINE);
    expect(model.payment).toEqual({
      id: "pay-1",
      status: "pending",
      provider: "mock",
      redirectUrl: "http://localhost:3000/checkout/return?order=B3D-2026-000123",
    });
    expect(model.droppedProductIds).toEqual(["p-owned"]);
    expect(model.amountDue).toBeNull();
    expect(model.deliveryAddress).toBeNull();
    expect(model.next).toBe("online-redirect");
  });

  it("online with no redirect_url never pretends a payment page exists", () => {
    const model = adaptCheckoutRead({
      ...ONLINE,
      payment: { ...ONLINE.payment!, redirect_url: null },
    });
    expect(model.next).toBe("online-no-redirect");
  });

  it("online with an unsafe redirect_url is not followed", () => {
    const model = adaptCheckoutRead({
      ...ONLINE,
      payment: { ...ONLINE.payment!, redirect_url: "javascript:alert(1)" },
    });
    expect(model.next).toBe("online-no-redirect");
  });
});

describe("isFollowableRedirect", () => {
  it("accepts absolute http(s) URLs only, without inspecting their parameters", () => {
    expect(isFollowableRedirect("https://pay.example.com/p/1?status=success")).toBe(true);
    expect(isFollowableRedirect("http://localhost:3000/checkout/return?order=X")).toBe(true);
    expect(isFollowableRedirect("javascript:alert(1)")).toBe(false);
    expect(isFollowableRedirect("data:text/html,hi")).toBe(false);
    expect(isFollowableRedirect("/relative")).toBe(false);
    expect(isFollowableRedirect("")).toBe(false);
  });
});
