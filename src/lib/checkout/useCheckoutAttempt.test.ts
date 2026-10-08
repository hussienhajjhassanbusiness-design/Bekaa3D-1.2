import { describe, it, expect, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useCheckoutAttempt } from "./useCheckoutAttempt";

// FVS-026-IMPLEMENTATION-PLAN.md T01 — #SECURITY-CHECKOUT-IDEMPOTENCY.
// `attemptKey` is generated exactly once via React's lazy useState
// initializer (never on every render); `startNewAttempt()` is the
// ONE explicit, caller-driven way to retire the current key. This
// file never references a backend header/body field name — attempt-
// key generation is deliberately separate from request/header
// mapping (a future adapter's job, blocked on the backend contract).

describe("useCheckoutAttempt", () => {
  it("generates a key once and returns the same key across re-renders (a retry)", () => {
    const { result, rerender } = renderHook(() => useCheckoutAttempt());
    const firstKey = result.current.attemptKey;

    rerender();

    expect(result.current.attemptKey).toBe(firstKey);
  });

  it("generates a plausible, non-empty key", () => {
    const { result } = renderHook(() => useCheckoutAttempt());
    expect(typeof result.current.attemptKey).toBe("string");
    expect(result.current.attemptKey.length).toBeGreaterThan(0);
  });

  it("startNewAttempt() produces a different key, retiring the old one", () => {
    const { result } = renderHook(() => useCheckoutAttempt());
    const firstKey = result.current.attemptKey;

    act(() => {
      result.current.startNewAttempt();
    });

    expect(result.current.attemptKey).not.toBe(firstKey);
  });

  it("never calls startNewAttempt on its own — the key stays stable without caller action", () => {
    const { result, rerender } = renderHook(() => useCheckoutAttempt());
    const firstKey = result.current.attemptKey;

    rerender();
    rerender();
    rerender();

    expect(result.current.attemptKey).toBe(firstKey);
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    renderHook(() => useCheckoutAttempt());
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});
