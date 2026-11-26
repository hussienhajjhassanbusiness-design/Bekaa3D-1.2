import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useCooldown } from "./useCooldown";

// FVS-002-IMPLEMENTATION-PLAN.md §11 — absolute-deadline countdown, pure
// logic, no business-flow knowledge (resend/rate-limit copy lives in the
// consuming page, not here). Fake timers throughout; no real setInterval
// left running past a test (see afterEach).

afterEach(() => {
  vi.useRealTimers();
});

describe("useCooldown", () => {
  it("reports isActive: false and remainingSeconds: 0 when no deadline is given", () => {
    const { result } = renderHook(() => useCooldown(undefined));

    expect(result.current.isActive).toBe(false);
    expect(result.current.remainingSeconds).toBe(0);
  });

  it("reports the remaining seconds derived from Date.now() when a future deadline is given", () => {
    vi.useFakeTimers();
    vi.setSystemTime(0);

    const { result } = renderHook(() => useCooldown(120_000));

    expect(result.current.isActive).toBe(true);
    expect(result.current.remainingSeconds).toBe(120);
  });

  it("clamps remainingSeconds at zero for a deadline already in the past", () => {
    vi.useFakeTimers();
    vi.setSystemTime(10_000);

    const { result } = renderHook(() => useCooldown(0));

    expect(result.current.remainingSeconds).toBe(0);
    expect(result.current.isActive).toBe(false);
  });

  it("ticks down roughly in real time — after 60 seconds, about 60 seconds remain of a 120-second deadline", () => {
    vi.useFakeTimers();
    vi.setSystemTime(0);

    const { result } = renderHook(() => useCooldown(120_000));
    act(() => {
      vi.advanceTimersByTime(60_000);
    });

    expect(result.current.remainingSeconds).toBe(60);
    expect(result.current.isActive).toBe(true);
  });

  it("derives remaining time from the absolute deadline, so a throttled/background timer gap still lands on the correct value", () => {
    vi.useFakeTimers();
    vi.setSystemTime(0);

    const { result } = renderHook(() => useCooldown(120_000));
    // Simulate a single huge gap (e.g. a backgrounded tab), as if only one
    // tick fired after 100 real seconds instead of the usual 100 separate
    // 1-second ticks. The interval callback itself only fires once the fake
    // clock crosses its next scheduled 1000ms boundary, so real time at
    // fire-time is 101_000ms — remaining is computed from THAT real moment
    // (19s), not from a naively-incremented counter (which a drifting
    // implementation might have reported as ~119 ticks behind instead).
    act(() => {
      vi.setSystemTime(100_000);
      vi.advanceTimersByTime(1_000);
    });

    expect(result.current.remainingSeconds).toBe(19);
  });

  it("re-enables (isActive: false, remainingSeconds: 0) once the deadline passes", () => {
    vi.useFakeTimers();
    vi.setSystemTime(0);

    const { result } = renderHook(() => useCooldown(5_000));
    act(() => {
      vi.advanceTimersByTime(5_000);
    });

    expect(result.current.remainingSeconds).toBe(0);
    expect(result.current.isActive).toBe(false);
  });

  it("stops its internal timer once the deadline passes, never re-scheduling further ticks", () => {
    vi.useFakeTimers();
    vi.setSystemTime(0);
    const clearIntervalSpy = vi.spyOn(globalThis, "clearInterval");

    renderHook(() => useCooldown(2_000));
    act(() => {
      vi.advanceTimersByTime(2_000);
    });

    expect(clearIntervalSpy).toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("clears its timer on unmount and performs no further state updates", () => {
    vi.useFakeTimers();
    vi.setSystemTime(0);

    const { unmount } = renderHook(() => useCooldown(120_000));
    unmount();

    expect(vi.getTimerCount()).toBe(0);
  });

  it("recomputes cleanly when the deadline changes (e.g. a fresh cooldown starting after a prior one completed)", () => {
    vi.useFakeTimers();
    vi.setSystemTime(0);

    const { result, rerender } = renderHook(({ deadline }: { deadline: number | undefined }) => useCooldown(deadline), {
      initialProps: { deadline: undefined as number | undefined },
    });

    expect(result.current.isActive).toBe(false);

    rerender({ deadline: 120_000 });
    expect(result.current.isActive).toBe(true);
    expect(result.current.remainingSeconds).toBe(120);
  });
});
