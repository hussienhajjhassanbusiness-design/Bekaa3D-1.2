import { describe, it, expect } from "vitest";
import type { RefundModel, RefundLineBreakdownModel } from "./refundModel";

// FVS-032-IMPLEMENTATION-PLAN.md T01 — frontend-normalized refund
// shapes only, never a claim about RefundDetail/Page's real field
// names (unconfirmed). `isSettled` is an explicit, caller-supplied
// capability — never derived from `statusLabel` text
// (#SECURITY-REFUND-SETTLEMENT-SEPARATION): a refund record can
// exist (and have an id) without money having moved.

describe("RefundModel", () => {
  it("accepts the normalized refund-detail fields, with no provider secret/raw payload field", () => {
    const refund: RefundModel = {
      id: "refund-1",
      linkedOrderDisplayId: "order-1",
      statusLabel: "Pending settlement",
      isSettled: false,
      totalAmountCents: 2000,
      currency: "USD",
    };
    expect(refund.isSettled).toBe(false);
  });

  it("accepts optional settlementMethodLabel, lines breakdown, shippingAmountCents, reason, createdAtLabel", () => {
    const line: RefundLineBreakdownModel = {
      lineId: "line-1",
      productDisplayName: "Garden Gnome",
      amountCents: 1500,
      currency: "USD",
    };
    const refund: RefundModel = {
      id: "refund-1",
      linkedOrderDisplayId: "order-1",
      statusLabel: "Settled",
      isSettled: true,
      totalAmountCents: 2000,
      currency: "USD",
      settlementMethodLabel: "Manual",
      lines: [line],
      shippingAmountCents: 500,
      reason: "Damaged in transit",
      createdAtLabel: "Jan 1, 2026",
    };
    expect(refund.lines?.[0]?.productDisplayName).toBe("Garden Gnome");
  });

  it("isSettled is explicit — a pending refund can carry an id and amount without being settled", () => {
    const refund: RefundModel = {
      id: "refund-2",
      linkedOrderDisplayId: "order-2",
      statusLabel: "Pending settlement",
      isSettled: false,
      totalAmountCents: 999,
      currency: "USD",
    };
    expect(refund.id).toBeTruthy();
    expect(refund.isSettled).toBe(false);
  });
});
