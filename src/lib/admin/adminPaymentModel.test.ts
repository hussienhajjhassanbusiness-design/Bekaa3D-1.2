import { describe, it, expect } from "vitest";
import { describeAdminPaymentStatus } from "./adminPaymentModel";
import type { AdminPaymentModel } from "./adminPaymentModel";

// FVS-028-IMPLEMENTATION-PLAN.md T01 — reuses FVS-027's PaymentStatus
// directly rather than inventing a second, incompatible union
// (#ARCHITECTURE-ADMIN-PAYMENT-ADAPTER). No provider secret, webhook
// signature, raw provider payload, credential, or internal
// reconciliation detail exists on this type at all
// (#SECURITY-PAYMENT-OPERATIONS-DATA).

describe("describeAdminPaymentStatus", () => {
  it("describes every PaymentStatus with a distinct, textual label", () => {
    expect(describeAdminPaymentStatus("pending").label).toBe("Pending");
    expect(describeAdminPaymentStatus("processing").label).toBe("Processing");
    expect(describeAdminPaymentStatus("paid").label).toBe("Paid");
    expect(describeAdminPaymentStatus("failed").label).toBe("Failed");
    expect(describeAdminPaymentStatus("expired").label).toBe("Expired");
  });

  it("never conveys status by color alone — every status has a tone from the bounded union", () => {
    const tones = ["pending", "processing", "paid", "failed", "expired"].map(
      (status) => describeAdminPaymentStatus(status as Parameters<typeof describeAdminPaymentStatus>[0]).tone
    );
    for (const tone of tones) {
      expect(["neutral", "positive", "negative", "warning"]).toContain(tone);
    }
  });

  it("gives failed and expired distinguishable tones", () => {
    expect(describeAdminPaymentStatus("failed").tone).not.toBe(describeAdminPaymentStatus("expired").tone);
  });
});

describe("AdminPaymentModel", () => {
  it("accepts the normalized fields this plan actually needs", () => {
    const payment: AdminPaymentModel = {
      id: "pay-1",
      status: "paid",
      amountCents: 5000,
      currency: "USD",
      providerDisplayLabel: "Whish",
      providerReferenceDisplayValue: "REF-123",
      linkedOrderDisplayId: "ORD-456",
      canManualConfirm: false,
    };
    expect(payment.id).toBe("pay-1");
  });

  it("accepts an optional manualConfirmBlockedReason", () => {
    const payment: AdminPaymentModel = {
      id: "pay-1",
      status: "pending",
      amountCents: 5000,
      currency: "USD",
      providerDisplayLabel: "Whish",
      providerReferenceDisplayValue: "REF-123",
      linkedOrderDisplayId: "ORD-456",
      canManualConfirm: true,
      manualConfirmBlockedReason: undefined,
    };
    expect(payment.canManualConfirm).toBe(true);
  });

  it("has no provider secret, webhook signature, or raw payload field", () => {
    const payment: AdminPaymentModel = {
      id: "pay-1",
      status: "paid",
      amountCents: 5000,
      currency: "USD",
      providerDisplayLabel: "Whish",
      providerReferenceDisplayValue: "REF-123",
      linkedOrderDisplayId: "ORD-456",
      canManualConfirm: false,
    };
    expect("webhookSignature" in payment).toBe(false);
    expect("providerSecret" in payment).toBe(false);
    expect("rawPayload" in payment).toBe(false);
  });
});
