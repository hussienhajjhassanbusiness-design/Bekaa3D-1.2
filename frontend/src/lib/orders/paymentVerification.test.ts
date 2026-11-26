import { describe, expect, it } from "vitest";
import { detailDTO, pendingOnlineDetailDTO } from "./orderFixtures";
import { isPaymentTransient, onlinePaymentState, PAYMENT_POLLING } from "./paymentVerification";

const usd = (amount_cents: number) => ({ amount_cents, currency: "USD" });

describe("isPaymentTransient", () => {
  it("is true for an online pending_payment order whose attempt is pending or processing", () => {
    expect(isPaymentTransient(pendingOnlineDetailDTO())).toBe(true);
    expect(
      isPaymentTransient(pendingOnlineDetailDTO({ payment: { status: "processing", provider: "mock", amount: usd(2500) } }))
    ).toBe(true);
  });

  it("is false once the payment is terminal", () => {
    for (const status of ["paid", "failed", "expired", "refunded", "partially_refunded", "something_new"]) {
      expect(isPaymentTransient(pendingOnlineDetailDTO({ payment: { status, provider: "mock", amount: usd(2500) } }))).toBe(
        false
      );
    }
  });

  it("is false once the order is no longer pending_payment or was cancelled", () => {
    expect(isPaymentTransient(pendingOnlineDetailDTO({ status: "in_progress" }))).toBe(false);
    expect(isPaymentTransient(pendingOnlineDetailDTO({ status: "cancelled" }))).toBe(false);
    expect(isPaymentTransient(pendingOnlineDetailDTO({ cancelled_at: "2026-11-10T10:05:00Z" }))).toBe(false);
  });

  it("is never true for cash, for no payment row, or with no data", () => {
    expect(isPaymentTransient(detailDTO())).toBe(false);
    expect(
      isPaymentTransient(
        detailDTO({ status: "pending_payment", payment: { status: "pending", provider: "cash", amount: usd(2500) } })
      )
    ).toBe(false);
    expect(isPaymentTransient(pendingOnlineDetailDTO({ payment: null }))).toBe(false);
    expect(isPaymentTransient(undefined)).toBe(false);
    expect(isPaymentTransient(null)).toBe(false);
  });
});

describe("onlinePaymentState", () => {
  it("maps every backend PaymentStatus and degrades anything else to unknown", () => {
    expect(onlinePaymentState("pending")).toBe("awaiting");
    expect(onlinePaymentState("processing")).toBe("processing");
    expect(onlinePaymentState("paid")).toBe("paid");
    expect(onlinePaymentState("failed")).toBe("failed");
    expect(onlinePaymentState("expired")).toBe("expired");
    expect(onlinePaymentState("refunded")).toBe("refunded");
    expect(onlinePaymentState("partially_refunded")).toBe("partially-refunded");
    expect(onlinePaymentState("chargeback")).toBe("unknown");
    expect(onlinePaymentState("constructor")).toBe("unknown");
    expect(onlinePaymentState(null)).toBe("none");
  });
});

describe("PAYMENT_POLLING", () => {
  it("is bounded and backs off", () => {
    expect(PAYMENT_POLLING.maxDurationMs).toBeLessThanOrEqual(5 * 60_000);
    expect(PAYMENT_POLLING.slowIntervalMs).toBeGreaterThan(PAYMENT_POLLING.fastIntervalMs);
    expect(PAYMENT_POLLING.fastPhaseMs).toBeLessThan(PAYMENT_POLLING.maxDurationMs);
  });
});
