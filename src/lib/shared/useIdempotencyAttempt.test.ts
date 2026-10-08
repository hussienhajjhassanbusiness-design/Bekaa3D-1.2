import { describe, it, expect, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useIdempotencyAttempt } from "./useIdempotencyAttempt";

// FVS-032-IMPLEMENTATION-PLAN.md T08 — extracted from
// useCheckoutAttempt.ts (FVS-026), which was already fully domain-
// free in implementation; this is the second genuine reuse case
// (refund creation needs the identical primitive) that justifies the
// extraction. useCheckoutAttempt.ts now wraps this unchanged. Mirrors
// useCheckoutAttempt.test.ts's own assertions exactly — a pure
// extraction, not new behavior.

describe("useIdempotencyAttempt", () => {
  it("generates a key once and returns the same key across re-renders (a retry)", () => {
    const { result, rerender } = renderHook(() => useIdempotencyAttempt());
    const firstKey = result.current.attemptKey;

    rerender();

    expect(result.current.attemptKey).toBe(firstKey);
  });

  it("generates a plausible, non-empty key", () => {
    const { result } = renderHook(() => useIdempotencyAttempt());
    expect(typeof result.current.attemptKey).toBe("string");
    expect(result.current.attemptKey.length).toBeGreaterThan(0);
  });

  it("startNewAttempt() produces a different key, retiring the old one", () => {
    const { result } = renderHook(() => useIdempotencyAttempt());
    const firstKey = result.current.attemptKey;

    act(() => {
      result.current.startNewAttempt();
    });

    expect(result.current.attemptKey).not.toBe(firstKey);
  });

  it("never calls startNewAttempt on its own — the key stays stable without caller action", () => {
    const { result, rerender } = renderHook(() => useIdempotencyAttempt());
    const firstKey = result.current.attemptKey;

    rerender();
    rerender();
    rerender();

    expect(result.current.attemptKey).toBe(firstKey);
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    renderHook(() => useIdempotencyAttempt());
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});
