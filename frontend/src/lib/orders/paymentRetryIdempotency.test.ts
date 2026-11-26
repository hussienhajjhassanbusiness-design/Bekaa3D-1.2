import { describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { createPaymentRetryTracker, usePaymentRetryTracker } from "./paymentRetryIdempotency";
import { IDEMPOTENCY_KEY_PATTERN } from "@/lib/checkout/checkoutIdempotency";

// #SECURITY-PAYMENT-RETRY-IDEMPOTENCY — backend 2dfb27b
// (docs/payment-recovery.md, ordering/api/payment_retry.py): "One
// Idempotency-Key is one retry of one order by one user (scope
// payment_retry:{order_id})". The 201 and the 502 are replayed for the
// same key. The body is always `{}`, so the key is bound to the order.

function sequence() {
  let n = 0;
  return vi.fn(() => `retry-${String(++n).padStart(4, "0")}`);
}

describe("createPaymentRetryTracker", () => {
  it("mints a key for a new attempt and reuses it for an uncertain resend of the same attempt", () => {
    const generate = sequence();
    const tracker = createPaymentRetryTracker(generate);
    const first = tracker.keyFor("order-a");
    expect(first).toBe("retry-0001");
    // network failure / timeout / in-progress: the attempt is still open.
    expect(tracker.keyFor("order-a")).toBe(first);
    expect(tracker.currentKey()).toBe(first);
    expect(generate).toHaveBeenCalledTimes(1);
  });

  it("a definitive answer retires the key, so the next press is a new attempt with a new key", () => {
    const tracker = createPaymentRetryTracker(sequence());
    const first = tracker.keyFor("order-a");
    tracker.retire();
    expect(tracker.currentKey()).toBeNull();
    const second = tracker.keyFor("order-a");
    expect(second).not.toBe(first);
  });

  it("never reuses a key across orders", () => {
    const tracker = createPaymentRetryTracker(sequence());
    const a = tracker.keyFor("order-a");
    const b = tracker.keyFor("order-b");
    expect(b).not.toBe(a);
    expect(tracker.keyFor("order-b")).toBe(b);
  });

  it("refuses a generated key that the backend pattern would reject", () => {
    const tracker = createPaymentRetryTracker(() => "short");
    expect(() => tracker.keyFor("order-a")).toThrow();
  });

  it("the default generator produces keys matching the backend pattern", () => {
    const tracker = createPaymentRetryTracker();
    expect(tracker.keyFor("order-a")).toMatch(IDEMPOTENCY_KEY_PATTERN);
  });

  it("is memory-only: nothing is written to web storage", () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const tracker = createPaymentRetryTracker();
    tracker.keyFor("order-a");
    tracker.retire();
    expect(setItem).not.toHaveBeenCalled();
    setItem.mockRestore();
  });
});

describe("usePaymentRetryTracker", () => {
  it("is stable across re-renders and fresh per mount", () => {
    const { result, rerender, unmount } = renderHook(() => usePaymentRetryTracker());
    const first = result.current;
    const key = first.keyFor("order-a");
    rerender();
    expect(result.current).toBe(first);
    expect(result.current.currentKey()).toBe(key);
    unmount();
    const { result: again } = renderHook(() => usePaymentRetryTracker());
    expect(again.current.currentKey()).toBeNull();
  });
});
