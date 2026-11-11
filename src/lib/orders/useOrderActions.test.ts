import { describe, it, expect, vi, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { ordersApi } from "./ordersApi";
import { orderKeys } from "./orderKeys";
import { detailDTO, ORDER_ID } from "./orderFixtures";
import { ORDER_ACTION_MESSAGES } from "./orderActionErrors";
import { useOrderAction } from "./useOrderActions";

const http = (status: number, code: string, extra: Record<string, unknown> = {}) => ({
  kind: "http" as const,
  status,
  code,
  message: "RAW",
  raw: { status, code, ...extra },
});

function setup<A extends "cancel" | "confirm-receipt" | "report-problem">(action: A) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(queryClient, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
  const hook = renderHook(() => useOrderAction(ORDER_ID, action), { wrapper });
  return { ...hook, invalidate, queryClient };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useOrderAction", () => {
  it("cancel: writes the server's OrderDetail into the canonical detail cache and re-reads the order family", async () => {
    const cancelled = detailDTO({ status: "cancelled", can_cancel: false });
    const spy = vi.spyOn(ordersApi, "cancelOrder").mockResolvedValue(cancelled);
    const { result, invalidate, queryClient } = setup("cancel");

    let ok = false;
    await act(async () => {
      ok = await result.current.submit();
    });

    expect(ok).toBe(true);
    expect(spy).toHaveBeenCalledWith(ORDER_ID, undefined);
    expect(queryClient.getQueryData(orderKeys.detail(ORDER_ID))).toBe(cancelled);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: orderKeys.root });
    expect(result.current.state).toEqual({ kind: "success" });
  });

  it("report-problem: sends the message through unchanged", async () => {
    const spy = vi.spyOn(ordersApi, "reportProblem").mockResolvedValue(detailDTO());
    const { result } = setup("report-problem");
    await act(async () => {
      await result.current.submit("Lid cracked\nplease help");
    });
    expect(spy).toHaveBeenCalledWith(ORDER_ID, "Lid cracked\nplease help");
  });

  it("confirm-receipt: calls the receipt route", async () => {
    const spy = vi.spyOn(ordersApi, "confirmReceipt").mockResolvedValue(detailDTO());
    const { result } = setup("confirm-receipt");
    await act(async () => {
      await result.current.submit();
    });
    expect(spy).toHaveBeenCalledWith(ORDER_ID);
  });

  it("ignores a second submit while the first is in flight (double click)", async () => {
    let resolve: (v: ReturnType<typeof detailDTO>) => void = () => {};
    const spy = vi
      .spyOn(ordersApi, "cancelOrder")
      .mockImplementation(() => new Promise((r) => (resolve = r)));
    const { result } = setup("cancel");

    let first: Promise<boolean> = Promise.resolve(false);
    let second = true;
    await act(async () => {
      first = result.current.submit();
      second = await result.current.submit();
    });
    expect(second).toBe(false);
    expect(result.current.state).toEqual({ kind: "pending" });
    await act(async () => {
      resolve(detailDTO());
      await first;
    });
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("a refusal surfaces safe copy, re-reads the order, and allows another attempt", async () => {
    const spy = vi
      .spyOn(ordersApi, "confirmReceipt")
      .mockRejectedValueOnce(http(409, "INVALID_STATE_TRANSITION", { reason: "no_delivered_line" }))
      .mockResolvedValueOnce(detailDTO());
    const { result, invalidate } = setup("confirm-receipt");

    let ok = true;
    await act(async () => {
      ok = await result.current.submit();
    });
    expect(ok).toBe(false);
    expect(result.current.state).toEqual({
      kind: "error",
      outcome: { kind: "refused", message: ORDER_ACTION_MESSAGES.noDeliveredLine, refetchOrder: true },
    });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: orderKeys.root });

    await act(async () => {
      ok = await result.current.submit();
    });
    expect(ok).toBe(true);
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it("a CSRF failure does not re-read the order; reset() clears the error", async () => {
    vi.spyOn(ordersApi, "cancelOrder").mockRejectedValue(http(403, "CSRF_INVALID"));
    const { result, invalidate } = setup("cancel");
    await act(async () => {
      await result.current.submit();
    });
    expect(result.current.state.kind).toBe("error");
    expect(invalidate).not.toHaveBeenCalled();
    act(() => result.current.reset());
    expect(result.current.state).toEqual({ kind: "idle" });
  });
});
