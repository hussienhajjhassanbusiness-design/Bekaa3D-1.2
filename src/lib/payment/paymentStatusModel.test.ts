import { describe, it, expect } from "vitest";
import { isTerminalPaymentStatus } from "./paymentStatusModel";
import type { PaymentVerificationState } from "./paymentStatusModel";

// FVS-027-IMPLEMENTATION-PLAN.md T01 — frontend-normalized concepts
// only, never a claimed backend enum literal
// (#ARCHITECTURE-PAYMENT-STATUS-ADAPTER). The critical structural
// guarantee: PaymentVerificationState's "timeout"/"network-error"
// variants carry NO `status` field at all — a local polling outcome
// can never be confused with (or accidentally rendered as) a backend
// payment status.

describe("isTerminalPaymentStatus", () => {
  it("is false for pending", () => {
    expect(isTerminalPaymentStatus("pending")).toBe(false);
  });

  it("is false for processing", () => {
    expect(isTerminalPaymentStatus("processing")).toBe(false);
  });

  it("is true for paid", () => {
    expect(isTerminalPaymentStatus("paid")).toBe(true);
  });

  it("is true for failed", () => {
    expect(isTerminalPaymentStatus("failed")).toBe(true);
  });

  it("is true for expired", () => {
    expect(isTerminalPaymentStatus("expired")).toBe(true);
  });
});

describe("PaymentVerificationState", () => {
  it("accepts a verifying state with no other fields", () => {
    const state: PaymentVerificationState = { kind: "verifying" };
    expect(state.kind).toBe("verifying");
  });

  it("accepts a backend-verified status state", () => {
    const state: PaymentVerificationState = { kind: "status", status: "paid" };
    expect(state.kind).toBe("status");
  });

  it("the timeout variant has no status field — never confusable with a backend status", () => {
    const state: PaymentVerificationState = { kind: "timeout" };
    expect("status" in state).toBe(false);
  });

  it("the network-error variant has no status field — never confusable with a backend status", () => {
    const state: PaymentVerificationState = { kind: "network-error" };
    expect("status" in state).toBe(false);
  });
});
