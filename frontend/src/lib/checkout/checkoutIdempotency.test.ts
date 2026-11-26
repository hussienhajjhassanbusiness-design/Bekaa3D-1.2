import { describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import {
  IDEMPOTENCY_KEY_PATTERN,
  checkoutFingerprint,
  createCheckoutAttemptTracker,
  useCheckoutAttemptTracker,
} from "./checkoutIdempotency";
import type { CheckoutRequestDTO } from "./checkoutTypes";

// #SECURITY-CHECKOUT-IDEMPOTENCY — backend 2dfb27b (docs/checkout.md,
// ordering/api/checkout.py): "One key per 'Place order' press and all its
// automatic retries; a new key after any change." The server hashes the
// body under the key: same key + same body replays the stored 201/502,
// same key + different body is 409 IDEMPOTENCY_KEY_CONFLICT. So the key is
// bound to the exact body it was minted for.

const BODY: CheckoutRequestDTO = {
  payment_method: "online",
  accept_terms: true,
  accept_digital_final_sale: true,
};

function sequence() {
  let n = 0;
  return vi.fn(() => `key-${String(++n).padStart(4, "0")}`);
}

describe("createCheckoutAttemptTracker", () => {
  it("mints a key on the first submission and reuses it for a retry of the identical body", () => {
    const generate = sequence();
    const tracker = createCheckoutAttemptTracker(generate);
    const first = tracker.keyFor(BODY);
    const retry = tracker.keyFor({ ...BODY });
    expect(first).toBe("key-0001");
    expect(retry).toBe(first);
    expect(generate).toHaveBeenCalledTimes(1);
  });

  it("the same body with keys in a different order is the same attempt", () => {
    const tracker = createCheckoutAttemptTracker(sequence());
    const a = tracker.keyFor({ payment_method: "online", accept_terms: true });
    const b = tracker.keyFor({ accept_terms: true, payment_method: "online" });
    expect(b).toBe(a);
  });

  it("mints a NEW key when anything in the body changes (e.g. accepted_price_changes added)", () => {
    const tracker = createCheckoutAttemptTracker(sequence());
    const first = tracker.keyFor(BODY);
    const accepted = tracker.keyFor({
      ...BODY,
      accepted_price_changes: [{ product_id: "p-1", amount_cents: 2100, currency: "USD" }],
    });
    expect(accepted).not.toBe(first);
  });

  it("retire() forgets the key so a genuinely new checkout gets a fresh one", () => {
    const tracker = createCheckoutAttemptTracker(sequence());
    const first = tracker.keyFor(BODY);
    tracker.retire();
    expect(tracker.currentKey()).toBeNull();
    expect(tracker.keyFor(BODY)).not.toBe(first);
  });

  it("the default generator produces keys the backend pattern accepts (8-255 of [A-Za-z0-9._:-])", () => {
    const tracker = createCheckoutAttemptTracker();
    const key = tracker.keyFor(BODY);
    expect(key).toMatch(IDEMPOTENCY_KEY_PATTERN);
    expect(IDEMPOTENCY_KEY_PATTERN.test("short")).toBe(false);
    expect(IDEMPOTENCY_KEY_PATTERN.test("has space in it")).toBe(false);
  });

  it("refuses to hand out a key the backend would reject", () => {
    const tracker = createCheckoutAttemptTracker(() => "bad key!");
    expect(() => tracker.keyFor(BODY)).toThrow();
  });
});

describe("checkoutFingerprint", () => {
  it("is order-insensitive for object keys but order-sensitive for arrays", () => {
    expect(checkoutFingerprint({ a: 1, b: [1, 2] } as never)).toBe(checkoutFingerprint({ b: [1, 2], a: 1 } as never));
    expect(checkoutFingerprint({ b: [1, 2] } as never)).not.toBe(checkoutFingerprint({ b: [2, 1] } as never));
  });
});

describe("useCheckoutAttemptTracker", () => {
  it("is the same tracker across re-renders, so a re-render never mints a new key", () => {
    const { result, rerender } = renderHook(() => useCheckoutAttemptTracker());
    const tracker = result.current;
    const key = tracker.keyFor(BODY);
    rerender();
    rerender();
    expect(result.current).toBe(tracker);
    expect(result.current.keyFor(BODY)).toBe(key);
  });

  it("is never persisted: a fresh mount (reload / new visit) starts with no key", () => {
    const first = renderHook(() => useCheckoutAttemptTracker());
    first.result.current.keyFor(BODY);
    first.unmount();
    const second = renderHook(() => useCheckoutAttemptTracker());
    expect(second.result.current.currentKey()).toBeNull();
  });
});
