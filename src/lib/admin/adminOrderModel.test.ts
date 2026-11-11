import { describe, it, expect } from "vitest";
import type { AdminOrderLineModel, AdminOrderModel, TransitionAffordance } from "./adminOrderModel";
import type { OrderLineItemProps } from "@/components/account/OrderLineItem";
import type { OrderDetailViewProps } from "@/components/account/OrderDetailView";

// FVS-030-IMPLEMENTATION-PLAN.md T01 — AdminOrderLineModel reuses
// FVS-029's OrderLineModel directly via extension, never a forked
// copy (#ARCHITECTURE-ADMIN-ORDER-PROJECTION). TransitionAffordance
// is a frontend-normalized, server-authoritative action — never
// derived from status locally (#SECURITY-SERVER-FULFILLMENT-STATE-MACHINE).
// The critical cross-slice regression test proves FVS-029's customer
// components have NO internal-note prop/render path at all — not
// merely "don't currently use one" (#SECURITY-INTERNAL-NOTE-BOUNDARY).

describe("TransitionAffordance", () => {
  it("accepts a server-authoritative action", () => {
    const action: TransitionAffordance = { id: "move-to-production", label: "Move to production", requiresConfirmation: false };
    expect(action.id).toBe("move-to-production");
  });
});

describe("AdminOrderLineModel", () => {
  it("accepts every OrderLineModel field plus availableActions — a genuine extension, not a duplication", () => {
    const line: AdminOrderLineModel = {
      id: "line-1",
      productDisplayName: "Garden Gnome",
      productType: "physical",
      quantity: 1,
      unitPriceCents: 1999,
      lineTotalCents: 1999,
      currency: "USD",
      statusLabel: "Processing",
      availableActions: [{ id: "move-to-production", label: "Move to production", requiresConfirmation: false }],
    };
    expect(line.productDisplayName).toBe("Garden Gnome");
  });

  it("accepts an empty availableActions array — a digital/STL line may legitimately have none", () => {
    const line: AdminOrderLineModel = {
      id: "line-2",
      productDisplayName: "Dragon STL",
      productType: "stl",
      quantity: 1,
      unitPriceCents: 500,
      lineTotalCents: 500,
      currency: "USD",
      statusLabel: "Delivered",
      availableActions: [],
    };
    expect(line.availableActions).toHaveLength(0);
  });

  it("accepts an optional adminCancelAction and refundObligationMessage (FVS-031) without requiring them", () => {
    const line: AdminOrderLineModel = {
      id: "line-3",
      productDisplayName: "Garden Gnome",
      productType: "physical",
      quantity: 1,
      unitPriceCents: 1999,
      lineTotalCents: 1999,
      currency: "USD",
      statusLabel: "In production",
      availableActions: [],
      adminCancelAction: { id: "admin-cancel", label: "Cancel order line", requiresConfirmation: true },
      refundObligationMessage: "Cancelling after production may require a refund.",
    };
    expect(line.adminCancelAction?.id).toBe("admin-cancel");

    const lineWithoutCancel: AdminOrderLineModel = {
      ...line,
      id: "line-4",
      adminCancelAction: undefined,
      refundObligationMessage: undefined,
    };
    expect(lineWithoutCancel.adminCancelAction).toBeUndefined();
  });
});

describe("AdminOrderModel", () => {
  it("accepts the normalized fields this plan actually needs, reusing OrderSummaryModel directly", () => {
    const order: AdminOrderModel = {
      id: "order-1",
      displayDate: "Oct 7, 2026",
      statusLabel: "Processing",
      lines: [],
      summary: { currency: "USD" },
      internalNote: "",
    };
    expect(order.internalNote).toBe("");
  });
});

describe("Customer/admin order boundary regression (#SECURITY-INTERNAL-NOTE-BOUNDARY)", () => {
  it("FVS-029's OrderLineItemProps structurally cannot carry an internal note", () => {
    // @ts-expect-error — OrderLineItemProps has no internalNote field
    const attempted: OrderLineItemProps = { line: {} as never, internalNote: "leaked" };
    expect(attempted).toBeDefined();
  });

  it("FVS-029's OrderDetailViewProps structurally cannot carry an internal note", () => {
    // @ts-expect-error — OrderDetailViewProps has no internalNote field
    const attempted: OrderDetailViewProps = { order: {} as never, internalNote: "leaked" };
    expect(attempted).toBeDefined();
  });
});
