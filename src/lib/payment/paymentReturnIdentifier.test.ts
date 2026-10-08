import { describe, it, expect } from "vitest";
import { extractReturnIdentifier } from "./paymentReturnIdentifier";

// FVS-027-IMPLEMENTATION-PLAN.md T02 — #SECURITY-PAYMENT-RETURN-UNTRUSTED.
// An identification helper ONLY — it must never inspect, branch on,
// or be influenced by any status-like field. This is the exact
// boundary that keeps a manipulated return URL from ever being able
// to assert payment truth.

describe("extractReturnIdentifier", () => {
  it("extracts the configured key's value", () => {
    const params = new URLSearchParams("order_id=abc123");
    expect(extractReturnIdentifier(params, "order_id")).toBe("abc123");
  });

  it("returns null when the key is absent", () => {
    const params = new URLSearchParams("");
    expect(extractReturnIdentifier(params, "order_id")).toBeNull();
  });

  it("is completely unaffected by success-looking parameters alongside the identifier", () => {
    const params = new URLSearchParams("order_id=abc123&status=success&paid=true&payment_status=paid");
    expect(extractReturnIdentifier(params, "order_id")).toBe("abc123");
  });

  it("is completely unaffected by success-looking parameters when the configured key is absent", () => {
    const params = new URLSearchParams("status=success&paid=true&payment_status=paid");
    expect(extractReturnIdentifier(params, "order_id")).toBeNull();
  });
});
