import { describe, it, expect } from "vitest";
import { adaptOrderDetail, adaptOrderSummary, isOrderId } from "./orderModel";
import { detailDTO, lineDTO, pendingOnlineDetailDTO, stlLineDTO, summaryDTO } from "./orderFixtures";

describe("adaptOrderSummary", () => {
  it("maps every server field, with money as integer cents untouched", () => {
    expect(adaptOrderSummary(summaryDTO())).toEqual({
      id: "0b6f2a52-7f5d-4f3e-9c55-3b8b1f5d2a10",
      orderNumber: "B3D-2026-000123",
      status: "in_progress",
      paymentMethod: "cash",
      fulfillmentMethod: "delivery",
      paymentDue: true,
      amountDue: { amountCents: 2500, currency: "USD" },
      total: { amountCents: 2500, currency: "USD" },
      placedAt: "2026-11-10T09:30:00Z",
    });
  });

  it("keeps a null amount_due and fulfillment_method as null", () => {
    const model = adaptOrderSummary(
      summaryDTO({ payment_method: "online", payment_due: false, amount_due: null, fulfillment_method: null })
    );
    expect(model.amountDue).toBeNull();
    expect(model.fulfillmentMethod).toBeNull();
  });
});

describe("adaptOrderDetail", () => {
  it("maps a cash delivery order without inventing a payment", () => {
    const model = adaptOrderDetail(detailDTO());
    expect(model.payment).toBeNull();
    expect(model.paymentDue).toBe(true);
    expect(model.amountDue).toEqual({ amountCents: 2500, currency: "USD" });
    expect(model.deliveryAddress).toEqual({
      recipientName: "Rana Haddad",
      lines: ["Main Street 12, Hoch el Oumara", "Zahle, Bekaa", "Blue gate"],
    });
    expect(model.hasDeliveryFeeNote).toBe(true);
    expect(model.contactPhone).toBe("+96170123456");
    expect(model.customerNote).toBe("Please call before delivery");
    expect(model.estimatedDispatchAt).toBe("2026-11-14T00:00:00Z");
    expect(model.subtotal).toEqual({ amountCents: 2500, currency: "USD" });
    expect(model.tax).toEqual({ amountCents: 0, currency: "USD" });
  });

  it("does not expose the advisory action flags (actions are later phases)", () => {
    const model = adaptOrderDetail(detailDTO({ can_cancel: true, can_retry_payment: true }));
    expect(model).not.toHaveProperty("canCancel");
    expect(model).not.toHaveProperty("canRetryPayment");
  });

  it("maps a pending online order's payment row exactly as given", () => {
    const model = adaptOrderDetail(pendingOnlineDetailDTO());
    expect(model.status).toBe("pending_payment");
    expect(model.payment).toEqual({ status: "pending", provider: "mock", amount: { amountCents: 2500, currency: "USD" } });
    expect(model.holdExpiresAt).toBe("2026-11-10T10:00:00Z");
  });

  it("drops empty address parts and tolerates an all-null snapshot", () => {
    const model = adaptOrderDetail(
      detailDTO({
        delivery_address: {
          recipient_name: null,
          governorate: null,
          city: null,
          area: null,
          street: null,
          landmark_notes: null,
        },
      })
    );
    expect(model.deliveryAddress).toEqual({ recipientName: null, lines: [] });
  });

  it("maps a pickup order with no address", () => {
    const model = adaptOrderDetail(
      detailDTO({ fulfillment_method: "pickup", delivery_address: null, delivery_fee_note: null })
    );
    expect(model.fulfillmentMethod).toBe("pickup");
    expect(model.deliveryAddress).toBeNull();
    expect(model.hasDeliveryFeeNote).toBe(false);
  });

  it("maps STL and physical lines with their snapshot fields", () => {
    const model = adaptOrderDetail(
      detailDTO({
        lines: [
          lineDTO({ receipt_confirmed_at: "2026-11-12T10:00:00Z" }),
          stlLineDTO({ fulfillment_status: "delivered", fulfilled_at: "2026-11-11T08:00:00Z" }),
        ],
      })
    );
    expect(model.lines[0]).toMatchObject({
      productType: "physical",
      name: "Cedar Planter",
      imageUrl: "https://media.example/planter.jpg",
      unitPrice: { amountCents: 1250, currency: "USD" },
      quantity: 2,
      lineTotal: { amountCents: 2500, currency: "USD" },
      fulfillmentStatus: "pending",
      receiptConfirmedAt: "2026-11-12T10:00:00Z",
    });
    expect(model.lines[1]).toMatchObject({ productType: "stl", fulfillmentStatus: "delivered", fulfilledAt: "2026-11-11T08:00:00Z" });
    expect(model.containsPhysical).toBe(true);
    expect(model.containsStl).toBe(true);
  });

  it("resolves line-level history entries to the line's name and type", () => {
    const model = adaptOrderDetail(
      detailDTO({
        lines: [stlLineDTO()],
        status_history: [
          { order_item_id: null, from_status: null, to_status: "in_progress", at: "2026-11-10T09:30:00Z" },
          { order_item_id: "line-stl-1", from_status: "pending", to_status: "awaiting_delivery", at: "2026-11-10T09:31:00Z" },
          { order_item_id: "unknown-line", from_status: null, to_status: "shipped", at: "2026-11-10T09:32:00Z" },
        ],
      })
    );
    expect(model.history).toEqual([
      { lineName: null, lineProductType: null, toStatus: "in_progress", at: "2026-11-10T09:30:00Z" },
      { lineName: "Dragon STL", lineProductType: "stl", toStatus: "awaiting_delivery", at: "2026-11-10T09:31:00Z" },
      { lineName: "An item", lineProductType: "physical", toStatus: "shipped", at: "2026-11-10T09:32:00Z" },
    ]);
  });

  it("maps refunds, and treats an absent refunds array as empty", () => {
    const withRefund = adaptOrderDetail(
      detailDTO({
        refunds: [
          { kind: "cancellation", status: "processing", amount: { amount_cents: 1250, currency: "USD" }, created_at: "2026-11-11T00:00:00Z" },
        ],
      })
    );
    expect(withRefund.refunds).toEqual([
      { kind: "cancellation", status: "processing", amount: { amountCents: 1250, currency: "USD" }, createdAt: "2026-11-11T00:00:00Z" },
    ]);
    const dto = detailDTO();
    delete dto.refunds;
    expect(adaptOrderDetail(dto).refunds).toEqual([]);
  });
});

describe("isOrderId", () => {
  it("accepts a UUID and rejects anything else (the backend 422s non-UUIDs)", () => {
    expect(isOrderId("0b6f2a52-7f5d-4f3e-9c55-3b8b1f5d2a10")).toBe(true);
    expect(isOrderId("0B6F2A52-7F5D-4F3E-9C55-3B8B1F5D2A10")).toBe(true);
    expect(isOrderId("123")).toBe(false);
    expect(isOrderId("../admin")).toBe(false);
    expect(isOrderId("")).toBe(false);
  });
});
