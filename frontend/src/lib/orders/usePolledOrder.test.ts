import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { ordersApi } from "./ordersApi";
import { usePolledOrder } from "./usePolledOrder";
import { orderKeys } from "./orderKeys";
import { detailDTO, ORDER_ID, pendingOnlineDetailDTO } from "./orderFixtures";
import { PAYMENT_POLLING } from "./paymentVerification";

const usd = (amount_cents: number) => ({ amount_cents, currency: "USD" });
const PAID = pendingOnlineDetailDTO({
  status: "in_progress",
  hold_expires_at: null,
  payment: { status: "paid", provider: "mock", amount: usd(2500) },
});

function setup() {
  const queryClient = new QueryClient();
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
  return { queryClient, wrapper };
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
  // A fetch settles through a few promise hops plus TanStack's
  // notifyManager setTimeout(0) batches: flush them without moving time.
  for (let i = 0; i < 3; i += 1) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
  }
}

// Phase timers are armed in effects after each render, so a window is
// walked phase by phase rather than in one jump.
async function runWindow() {
  await advance(0);
  await advance(PAYMENT_POLLING.fastPhaseMs);
  await advance(PAYMENT_POLLING.maxDurationMs - PAYMENT_POLLING.fastPhaseMs + 1_000);
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("usePolledOrder", () => {
  it("reads the canonical orderKeys.detail(id) query", async () => {
    vi.spyOn(ordersApi, "getMyOrder").mockResolvedValue(detailDTO());
    const { queryClient, wrapper } = setup();
    renderHook(() => usePolledOrder(ORDER_ID), { wrapper });
    await advance(0);
    expect(queryClient.getQueryData(orderKeys.detail(ORDER_ID))).toEqual(detailDTO());
  });

  it("never polls a cash order", async () => {
    const spy = vi.spyOn(ordersApi, "getMyOrder").mockResolvedValue(detailDTO());
    const { wrapper } = setup();
    const { result } = renderHook(() => usePolledOrder(ORDER_ID), { wrapper });
    await advance(0);
    expect(result.current.transient).toBe(false);
    expect(result.current.polling).toBe(false);
    await advance(60_000);
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("never polls an online order with no payment row", async () => {
    const spy = vi.spyOn(ordersApi, "getMyOrder").mockResolvedValue(pendingOnlineDetailDTO({ payment: null }));
    const { wrapper } = setup();
    renderHook(() => usePolledOrder(ORDER_ID), { wrapper });
    await advance(60_000);
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("re-reads a transient order and stops on the response that carries a terminal state", async () => {
    const spy = vi
      .spyOn(ordersApi, "getMyOrder")
      .mockResolvedValueOnce(pendingOnlineDetailDTO())
      .mockResolvedValueOnce(pendingOnlineDetailDTO({ payment: { status: "processing", provider: "mock", amount: usd(2500) } }))
      .mockResolvedValue(PAID);
    const { wrapper } = setup();
    const { result } = renderHook(() => usePolledOrder(ORDER_ID), { wrapper });
    await advance(0);
    expect(result.current.polling).toBe(true);
    await advance(PAYMENT_POLLING.fastIntervalMs);
    expect(spy).toHaveBeenCalledTimes(2);
    await advance(PAYMENT_POLLING.fastIntervalMs);
    expect(spy).toHaveBeenCalledTimes(3);
    expect(result.current.query.data?.payment?.status).toBe("paid");
    expect(result.current.polling).toBe(false);
    expect(result.current.timedOut).toBe(false);
    await advance(120_000);
    expect(spy).toHaveBeenCalledTimes(3);
  });

  it("stops when the order is released (cancelled) even if the payment row lags", async () => {
    const spy = vi
      .spyOn(ordersApi, "getMyOrder")
      .mockResolvedValueOnce(pendingOnlineDetailDTO())
      .mockResolvedValue(pendingOnlineDetailDTO({ status: "cancelled", cancelled_at: "2026-11-10T10:10:00Z" }));
    const { wrapper } = setup();
    const { result } = renderHook(() => usePolledOrder(ORDER_ID), { wrapper });
    await advance(PAYMENT_POLLING.fastIntervalMs);
    expect(spy).toHaveBeenCalledTimes(2);
    expect(result.current.polling).toBe(false);
    await advance(60_000);
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it("is bounded: fast, then slow, then stops with timedOut while still unresolved", async () => {
    const spy = vi.spyOn(ordersApi, "getMyOrder").mockResolvedValue(pendingOnlineDetailDTO());
    const { wrapper } = setup();
    const { result } = renderHook(() => usePolledOrder(ORDER_ID), { wrapper });
    await advance(0);
    await advance(PAYMENT_POLLING.fastPhaseMs);
    const afterFast = spy.mock.calls.length;
    expect(afterFast).toBe(1 + PAYMENT_POLLING.fastPhaseMs / PAYMENT_POLLING.fastIntervalMs);
    await advance(PAYMENT_POLLING.maxDurationMs - PAYMENT_POLLING.fastPhaseMs);
    expect(result.current.timedOut).toBe(true);
    expect(result.current.polling).toBe(false);
    const atStop = spy.mock.calls.length;
    // Slow phase is much sparser than the fast one.
    expect(atStop - afterFast).toBeLessThanOrEqual(
      Math.ceil((PAYMENT_POLLING.maxDurationMs - PAYMENT_POLLING.fastPhaseMs) / PAYMENT_POLLING.slowIntervalMs)
    );
    await advance(10 * 60_000);
    expect(spy.mock.calls.length).toBe(atStop);
    // The data is still the server's unresolved state, still usable.
    expect(result.current.query.data?.payment?.status).toBe("pending");
  });

  it("Check again re-reads now and opens one new bounded window", async () => {
    const spy = vi.spyOn(ordersApi, "getMyOrder").mockResolvedValue(pendingOnlineDetailDTO());
    const { wrapper } = setup();
    const { result } = renderHook(() => usePolledOrder(ORDER_ID), { wrapper });
    await runWindow();
    expect(result.current.timedOut).toBe(true);
    const before = spy.mock.calls.length;
    act(() => result.current.checkAgain());
    await advance(0);
    expect(spy.mock.calls.length).toBe(before + 1);
    expect(result.current.polling).toBe(true);
    expect(result.current.timedOut).toBe(false);
    await runWindow();
    expect(result.current.timedOut).toBe(true);
  });

  it("does not run for a disabled (malformed id) query", async () => {
    const spy = vi.spyOn(ordersApi, "getMyOrder").mockResolvedValue(pendingOnlineDetailDTO());
    const { wrapper } = setup();
    renderHook(() => usePolledOrder("bad", { enabled: false }), { wrapper });
    await advance(60_000);
    expect(spy).not.toHaveBeenCalled();
  });
});
