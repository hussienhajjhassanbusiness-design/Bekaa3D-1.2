import { describe, it, expect } from "vitest";
import { validateRefundLineAmount } from "./refundCreateModel";
import type { RefundLineCandidate } from "./refundCreateModel";

// FVS-032-IMPLEMENTATION-PLAN.md T01/T03 — RefundLineCandidate models
// a per-line refundable ceiling the SERVER supplies
// (#ARCHITECTURE-REFUND-LINE-CEILINGS); validateRefundLineAmount is a
// pure UX-only precheck — never authoritative
// (#SECURITY-REFUND-RACE-SERVER-WINS). It never clamps, never derives
// a ceiling from price, and a bug here can only reject a submission
// the server would have accepted, never approve one the server would
// reject.

describe("RefundLineCandidate", () => {
  it("accepts a server-supplied refundable ceiling with no derived amount", () => {
    const candidate: RefundLineCandidate = {
      lineId: "line-1",
      productDisplayName: "Garden Gnome",
      refundableBalanceCents: 1999,
      currency: "USD",
    };
    expect(candidate.refundableBalanceCents).toBe(1999);
  });

  it("accepts an optional isDigital flag", () => {
    const candidate: RefundLineCandidate = {
      lineId: "line-2",
      productDisplayName: "Dragon STL",
      refundableBalanceCents: 500,
      currency: "USD",
      isDigital: true,
    };
    expect(candidate.isDigital).toBe(true);
  });
});

describe("validateRefundLineAmount", () => {
  it("accepts an amount at or below the ceiling", () => {
    expect(validateRefundLineAmount(1000, 1999)).toEqual({ ok: true });
    expect(validateRefundLineAmount(1999, 1999)).toEqual({ ok: true });
  });

  it("accepts null (not refunding this line)", () => {
    expect(validateRefundLineAmount(null, 1999)).toEqual({ ok: true });
  });

  it("rejects an amount above the ceiling — a UX precheck only, never authoritative", () => {
    expect(validateRefundLineAmount(2000, 1999)).toEqual({ ok: false, reason: "exceeds-ceiling" });
  });

  it("rejects a negative amount", () => {
    expect(validateRefundLineAmount(-1, 1999)).toEqual({ ok: false, reason: "negative" });
  });

  it("never clamps or mutates the input — it only classifies", () => {
    const result = validateRefundLineAmount(2000, 1999);
    expect(result).not.toHaveProperty("cents");
  });
});
