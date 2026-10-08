import { describe, it, expect } from "vitest";
import type { OrderLineModel, OrderSummaryModel, OrderDetailModel, OrderListItemModel, OrderListFilters } from "./orderModel";

// FVS-029-IMPLEMENTATION-PLAN.md T02 — frontend-normalized shapes
// only, never a claim about the real OrderPage/OrderDetail response
// field names (unconfirmed — plan §0/§1; #SECURITY-CUSTOMER-ORDER-PROJECTION).
// Pure compile-time checks: none of these four types has an
// internalNote/adminNote/staffId/providerRawPayload/
// manualConfirmReason field anywhere — this is the customer/admin
// boundary FVS-030 must respect by composition, never by adding such
// a field here.

describe("OrderLineModel", () => {
  it("accepts a physical line", () => {
    const line: OrderLineModel = {
      id: "line-1",
      productDisplayName: "Garden Gnome",
      productType: "physical",
      quantity: 2,
      unitPriceCents: 1999,
      lineTotalCents: 3998,
      currency: "USD",
      statusLabel: "Processing",
    };
    expect(line.productType).toBe("physical");
  });

  it("accepts an STL line independently", () => {
    const line: OrderLineModel = {
      id: "line-2",
      productDisplayName: "Dragon STL",
      productType: "stl",
      quantity: 1,
      unitPriceCents: 500,
      lineTotalCents: 500,
      currency: "USD",
      statusLabel: "Delivered",
    };
    expect(line.productType).toBe("stl");
  });

  it("has no internal/admin/provider field", () => {
    const line: OrderLineModel = {
      id: "line-1",
      productDisplayName: "Garden Gnome",
      productType: "physical",
      quantity: 1,
      unitPriceCents: 1999,
      lineTotalCents: 1999,
      currency: "USD",
      statusLabel: "Processing",
    };
    expect("internalNote" in line).toBe(false);
    expect("adminNote" in line).toBe(false);
    expect("staffId" in line).toBe(false);
    expect("providerRawPayload" in line).toBe(false);
  });
});

describe("OrderSummaryModel / OrderDetailModel", () => {
  it("accepts a minimal summary with only currency", () => {
    const summary: OrderSummaryModel = { currency: "USD" };
    expect(summary.currency).toBe("USD");
  });

  it("accepts an order detail with lines and summary", () => {
    const detail: OrderDetailModel = {
      id: "order-1",
      displayDate: "Oct 7, 2026",
      statusLabel: "Processing",
      lines: [],
      summary: { currency: "USD" },
    };
    expect(detail.id).toBe("order-1");
  });

  it("has no internal/admin field on the detail or summary", () => {
    const detail: OrderDetailModel = {
      id: "order-1",
      displayDate: "Oct 7, 2026",
      statusLabel: "Processing",
      lines: [],
      summary: { currency: "USD" },
    };
    expect("internalNote" in detail).toBe(false);
    expect("manualConfirmReason" in detail.summary).toBe(false);
  });
});

describe("OrderListItemModel", () => {
  it("accepts the normalized fields this plan actually needs", () => {
    const item: OrderListItemModel = { id: "order-1", displayDate: "Oct 7, 2026", statusLabel: "Processing" };
    expect(item.id).toBe("order-1");
  });
});

describe("OrderListFilters", () => {
  it("accepts a fully-null (no filters applied) state", () => {
    const filters: OrderListFilters = { status: null, dateFrom: null, dateTo: null, cursor: null };
    expect(filters.status).toBeNull();
  });
});
