import { describe, it, expect } from "vitest";
import { orderKeys } from "./orderKeys";
import type { OrderListFilters } from "./orderModel";

// FVS-029-IMPLEMENTATION-PLAN.md T01 — the ONE canonical order query
// key (#ARCHITECTURE-CANONICAL-ORDERS-QUERY). If the backend later
// confirms GET /me/orders/{id} is also FVS-027's authoritative
// payment-verification read, FVS-027 MUST invalidate
// orderKeys.detail(id) rather than inventing a second cache for the
// same backend truth. Keys carry order id only, never address/
// customer PII, never a payment-provider reference.

const FILTERS: OrderListFilters = { status: null, dateFrom: null, dateTo: null, cursor: null };

describe("orderKeys", () => {
  it("has a stable root key", () => {
    expect(orderKeys.root).toEqual(["orders"]);
  });

  it("derives the list key from the canonical root, carrying the filters", () => {
    expect(orderKeys.list(FILTERS)).toEqual(["orders", "list", FILTERS]);
  });

  it("derives the detail key from the canonical root, keyed by the exact order id", () => {
    expect(orderKeys.detail("order-1")).toEqual(["orders", "detail", "order-1"]);
  });

  it("keeps list and detail keys distinguishable from each other and from the bare root", () => {
    const list = orderKeys.list(FILTERS);
    const detail = orderKeys.detail("order-1");
    const root = orderKeys.root;
    expect(list).not.toEqual(detail);
    expect(list).not.toEqual(root);
    expect(detail).not.toEqual(root);
  });

  it("produces deterministic, structurally-equal keys for two structurally-identical filter objects", () => {
    const a: OrderListFilters = { status: "paid", dateFrom: null, dateTo: null, cursor: null };
    const b: OrderListFilters = { status: "paid", dateFrom: null, dateTo: null, cursor: null };
    expect(orderKeys.list(a)).toEqual(orderKeys.list(b));
  });

  it("the detail key carries the order id only — no PII field is even possible given its shape", () => {
    const key = orderKeys.detail("order-1");
    expect(key).toHaveLength(3);
    expect(key[2]).toBe("order-1");
  });
});
