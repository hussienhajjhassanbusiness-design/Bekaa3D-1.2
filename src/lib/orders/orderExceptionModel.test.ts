import { describe, it, expect } from "vitest";
import { resolveCustomerCancelAction } from "./orderExceptionModel";
import type { CancellableOrderLineModel } from "./orderExceptionModel";

// FVS-031-IMPLEMENTATION-PLAN.md T01 — CancellableOrderLineModel
// extends FVS-029's OrderLineModel via composition, never a forked
// copy (#ARCHITECTURE-ORDER-EXCEPTION-ACTIONS). resolveCustomerCancelAction
// is a pure, UX-only defense-in-depth helper: it NEVER authorizes a
// cancellation server-side would reject, and it never fabricates an
// action the server did not supply — it can only suppress one.

describe("resolveCustomerCancelAction", () => {
  it("passes through a server-supplied action for a physical line", () => {
    const action = { id: "customer-cancel", label: "Cancel this item", requiresConfirmation: true };
    expect(resolveCustomerCancelAction({ productType: "physical" }, action)).toBe(action);
  });

  it("suppresses any action for an STL line, even one the server supplied — defense-in-depth UX only", () => {
    const action = { id: "customer-cancel", label: "Cancel this item", requiresConfirmation: true };
    expect(resolveCustomerCancelAction({ productType: "stl" }, action)).toBeNull();
  });

  it("passes through null unchanged for a physical line with no legal action", () => {
    expect(resolveCustomerCancelAction({ productType: "physical" }, null)).toBeNull();
  });

  it("never fabricates an action when none is supplied, even for a physical line", () => {
    expect(resolveCustomerCancelAction({ productType: "physical" }, null)).toBeNull();
  });
});

describe("CancellableOrderLineModel", () => {
  it("accepts every OrderLineModel field plus a resolved customerCancelAction", () => {
    const line: CancellableOrderLineModel = {
      id: "line-1",
      productDisplayName: "Garden Gnome",
      productType: "physical",
      quantity: 1,
      unitPriceCents: 1999,
      lineTotalCents: 1999,
      currency: "USD",
      statusLabel: "Processing",
      customerCancelAction: { id: "customer-cancel", label: "Cancel this item", requiresConfirmation: true },
    };
    expect(line.customerCancelAction?.id).toBe("customer-cancel");
  });

  it("accepts a null customerCancelAction", () => {
    const line: CancellableOrderLineModel = {
      id: "line-2",
      productDisplayName: "Dragon STL",
      productType: "stl",
      quantity: 1,
      unitPriceCents: 500,
      lineTotalCents: 500,
      currency: "USD",
      statusLabel: "Delivered",
      customerCancelAction: null,
    };
    expect(line.customerCancelAction).toBeNull();
  });
});
