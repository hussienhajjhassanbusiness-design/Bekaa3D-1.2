import { describe, it, expect } from "vitest";
import {
  describeLineStatus,
  describeOrderStatus,
  describePaymentStatus,
  describeRefundKind,
  describeRefundStatus,
  describeHistoryStatus,
} from "./orderStatus";

describe("describeOrderStatus", () => {
  it.each([
    ["pending_payment", "Awaiting payment", "warning"],
    ["in_progress", "In progress", "neutral"],
    ["completed", "Completed", "positive"],
    ["partially_refunded", "Partially refunded", "neutral"],
    ["refunded", "Refunded", "neutral"],
    ["cancelled", "Cancelled", "negative"],
  ] as const)("labels %s as %s", (status, label, tone) => {
    expect(describeOrderStatus(status)).toEqual({ label, tone });
  });

  it("degrades an unknown future value to a neutral label without echoing it", () => {
    expect(describeOrderStatus("on_hold_new_value")).toEqual({ label: "Status unavailable", tone: "neutral" });
  });

  it("does not treat an inherited Object key as a known status", () => {
    expect(describeOrderStatus("toString")).toEqual({ label: "Status unavailable", tone: "neutral" });
  });
});

describe("describePaymentStatus", () => {
  it.each([
    ["pending", "Awaiting payment", "warning"],
    ["processing", "Payment processing", "warning"],
    ["paid", "Paid", "positive"],
    ["partially_refunded", "Partially refunded", "neutral"],
    ["refunded", "Refunded", "neutral"],
    ["failed", "Payment failed", "negative"],
    ["expired", "Payment expired", "negative"],
  ] as const)("labels %s as %s", (status, label, tone) => {
    expect(describePaymentStatus(status)).toEqual({ label, tone });
  });

  it("degrades an unknown value safely", () => {
    expect(describePaymentStatus("chargeback_won")).toEqual({ label: "Status unavailable", tone: "neutral" });
  });
});

describe("describeLineStatus", () => {
  it("labels a pending line as Received (backend: printing reads pending)", () => {
    expect(describeLineStatus("pending", "physical").label).toBe("Received");
  });

  it("labels an STL awaiting_delivery line as not yet emailed", () => {
    expect(describeLineStatus("awaiting_delivery", "stl").label).toBe("Paid, not yet emailed");
  });

  it("labels a delivered STL line as emailed, never downloaded", () => {
    const { label, tone } = describeLineStatus("delivered", "stl");
    expect(label).toBe("Emailed");
    expect(tone).toBe("positive");
    expect(label.toLowerCase()).not.toContain("download");
  });

  it("labels a delivered physical line as Delivered", () => {
    expect(describeLineStatus("delivered", "physical").label).toBe("Delivered");
  });

  it.each([
    ["in_production", "In production"],
    ["ready_to_ship", "Ready to ship"],
    ["shipped", "Shipped"],
    ["returned", "Returned"],
    ["ready_for_pickup", "Ready for pickup"],
    ["picked_up", "Picked up"],
    ["cancelled", "Cancelled"],
    ["refunded", "Refunded"],
  ] as const)("labels %s as %s", (status, label) => {
    expect(describeLineStatus(status, "physical").label).toBe(label);
  });

  it("degrades an unknown value safely", () => {
    expect(describeLineStatus("teleported", "physical")).toEqual({ label: "Status unavailable", tone: "neutral" });
  });
});

describe("describeHistoryStatus", () => {
  it("uses order labels for order-level entries", () => {
    expect(describeHistoryStatus("in_progress", null)).toBe("In progress");
  });

  it("uses line labels for line-level entries", () => {
    expect(describeHistoryStatus("delivered", "stl")).toBe("Emailed");
    expect(describeHistoryStatus("shipped", "physical")).toBe("Shipped");
  });
});

describe("refund labels", () => {
  it("labels kinds and statuses, unknown degrade safely", () => {
    expect(describeRefundKind("cancellation")).toBe("Cancellation refund");
    expect(describeRefundKind("admin")).toBe("Refund");
    expect(describeRefundKind("late_capture")).toBe("Late payment refund");
    expect(describeRefundKind("other")).toBe("Refund");
    expect(describeRefundStatus("processing")).toBe("Processing");
    expect(describeRefundStatus("refunded")).toBe("Refunded");
    expect(describeRefundStatus("x")).toBe("Status unavailable");
  });
});
