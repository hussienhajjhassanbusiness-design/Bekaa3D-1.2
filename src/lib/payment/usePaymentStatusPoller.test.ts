import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { usePaymentStatusPoller } from "./usePaymentStatusPoller";
import type { PaymentStatus } from "./paymentStatusModel";

// FVS-027-IMPLEMENTATION-PLAN.md T03 — mirrors useScanStatusPolling's
// own "dumb hook, caller does the actual work" architecture exactly.
// `getDelayMs`/`maxDurationMs` are REQUIRED — no built-in production
// interval is hidden inside this hook. This hook never fetches or
// interprets a response; a network error is entirely the caller's
// own concern, surfaced one layer up as PaymentVerificationState's
// "network-error" kind, never as a status this hook invents.

const FIXED_DELAY = () => 1000;

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("usePaymentStatusPoller", () => {
  it("polls while status is null (nothing known yet)", () => {
    const onPoll = vi.fn();
    renderHook(() => usePaymentStatusPoller({ status: null, getDelayMs: FIXED_DELAY, maxDurationMs: 60_000, onPoll }));

    vi.advanceTimersByTime(1000);
    expect(onPoll).toHaveBeenCalledTimes(1);
  });

  it("polls while status is pending", () => {
    const onPoll = vi.fn();
    renderHook(() =>
      usePaymentStatusPoller({ status: "pending", getDelayMs: FIXED_DELAY, maxDurationMs: 60_000, onPoll })
    );

    vi.advanceTimersByTime(1000);
    expect(onPoll).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(1000);
    expect(onPoll).toHaveBeenCalledTimes(2);
  });

  it("polls while status is processing", () => {
    const onPoll = vi.fn();
    renderHook(() =>
      usePaymentStatusPoller({ status: "processing", getDelayMs: FIXED_DELAY, maxDurationMs: 60_000, onPoll })
    );

    vi.advanceTimersByTime(1000);
    expect(onPoll).toHaveBeenCalledTimes(1);
  });

  it("uses the supplied backoff policy exactly — delay grows per attempt", () => {
    const onPoll = vi.fn();
    const delays = [1000, 2000, 4000];
    const getDelayMs = vi.fn((attempt: number) => delays[attempt] ?? 4000);
    renderHook(() => usePaymentStatusPoller({ status: "pending", getDelayMs, maxDurationMs: 60_000, onPoll }));

    vi.advanceTimersByTime(1000);
    expect(onPoll).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(1999);
    expect(onPoll).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(1);
    expect(onPoll).toHaveBeenCalledTimes(2);

    vi.advanceTimersByTime(4000);
    expect(onPoll).toHaveBeenCalledTimes(3);
  });

  it("stops scheduling further polls once status becomes paid", () => {
    const onPoll = vi.fn();
    const { rerender } = renderHook(
      ({ status }: { status: PaymentStatus | null }) =>
        usePaymentStatusPoller({ status, getDelayMs: FIXED_DELAY, maxDurationMs: 60_000, onPoll }),
      { initialProps: { status: "pending" as PaymentStatus | null } }
    );

    vi.advanceTimersByTime(1000);
    expect(onPoll).toHaveBeenCalledTimes(1);

    rerender({ status: "paid" });
    onPoll.mockClear();
    vi.advanceTimersByTime(60_000);
    expect(onPoll).not.toHaveBeenCalled();
  });

  it("stops scheduling further polls once status becomes failed", () => {
    const onPoll = vi.fn();
    const { rerender } = renderHook(
      ({ status }: { status: PaymentStatus | null }) =>
        usePaymentStatusPoller({ status, getDelayMs: FIXED_DELAY, maxDurationMs: 60_000, onPoll }),
      { initialProps: { status: "pending" as PaymentStatus | null } }
    );
    vi.advanceTimersByTime(1000);
    rerender({ status: "failed" });
    onPoll.mockClear();
    vi.advanceTimersByTime(60_000);
    expect(onPoll).not.toHaveBeenCalled();
  });

  it("stops scheduling further polls once status becomes expired", () => {
    const onPoll = vi.fn();
    const { rerender } = renderHook(
      ({ status }: { status: PaymentStatus | null }) =>
        usePaymentStatusPoller({ status, getDelayMs: FIXED_DELAY, maxDurationMs: 60_000, onPoll }),
      { initialProps: { status: "pending" as PaymentStatus | null } }
    );
    vi.advanceTimersByTime(1000);
    rerender({ status: "expired" });
    onPoll.mockClear();
    vi.advanceTimersByTime(60_000);
    expect(onPoll).not.toHaveBeenCalled();
  });

  it("sets isTimedOut once maxDurationMs elapses while still non-terminal, and stops polling", () => {
    const onPoll = vi.fn();
    const { result } = renderHook(() =>
      usePaymentStatusPoller({ status: "pending", getDelayMs: FIXED_DELAY, maxDurationMs: 5000, onPoll })
    );

    act(() => {
      vi.advanceTimersByTime(5000);
    });

    expect(result.current.isTimedOut).toBe(true);
    onPoll.mockClear();
    vi.advanceTimersByTime(60_000);
    expect(onPoll).not.toHaveBeenCalled();
  });

  it("cleans up its timer on unmount — no poll fires after unmount", () => {
    const onPoll = vi.fn();
    const { unmount } = renderHook(() =>
      usePaymentStatusPoller({ status: "pending", getDelayMs: FIXED_DELAY, maxDurationMs: 60_000, onPoll })
    );

    unmount();
    vi.advanceTimersByTime(60_000);
    expect(onPoll).not.toHaveBeenCalled();
  });

  it("never schedules more than one outstanding timer — re-rendering with the same status does not multiply polls", () => {
    const onPoll = vi.fn();
    const { rerender } = renderHook(
      ({ status }: { status: PaymentStatus | null }) =>
        usePaymentStatusPoller({ status, getDelayMs: FIXED_DELAY, maxDurationMs: 60_000, onPoll }),
      { initialProps: { status: "pending" as PaymentStatus | null } }
    );

    rerender({ status: "pending" });
    rerender({ status: "pending" });

    vi.advanceTimersByTime(1000);
    expect(onPoll).toHaveBeenCalledTimes(1);
  });

  it("retry() clears isTimedOut and resumes polling", () => {
    const onPoll = vi.fn();
    const { result } = renderHook(() =>
      usePaymentStatusPoller({ status: "pending", getDelayMs: FIXED_DELAY, maxDurationMs: 5000, onPoll })
    );

    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(result.current.isTimedOut).toBe(true);

    act(() => {
      result.current.retry();
    });
    expect(result.current.isTimedOut).toBe(false);

    onPoll.mockClear();
    vi.advanceTimersByTime(1000);
    expect(onPoll).toHaveBeenCalledTimes(1);
  });
});
