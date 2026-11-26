import { describe, it, expect, vi, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { adminOrderKeys } from "./adminOrdersApi";
import { ADMIN_ORDER_MESSAGES } from "./adminOrderPresentation";
import { adminDetailDTO, ADMIN_ORDER_ID } from "./adminOrderFixtures";
import { useAdminOrderWrite } from "./useAdminOrders";
import type { AdminOrderDetailDTO } from "./adminOrderTypes";

function setup() {
  const queryClient = new QueryClient();
  const invalidate = vi.spyOn(queryClient, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client: queryClient }, children);
  const hook = renderHook(() => useAdminOrderWrite(), { wrapper });
  return { ...hook, queryClient, invalidate };
}

afterEach(() => vi.restoreAllMocks());

describe("useAdminOrderWrite", () => {
  it("stores the server's AdminOrderDetail and re-reads the admin order family", async () => {
    const { result, queryClient, invalidate } = setup();
    const next = adminDetailDTO({ status: "completed" });
    let ok = false;
    await act(async () => {
      ok = await result.current.run(() => Promise.resolve(next));
    });
    expect(ok).toBe(true);
    expect(queryClient.getQueryData(adminOrderKeys.detail(ADMIN_ORDER_ID))).toBe(next);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: adminOrderKeys.root });
    expect(result.current.state).toEqual({ kind: "idle" });
  });

  it("drops a second write while one is in flight", async () => {
    const { result } = setup();
    let resolve: (d: AdminOrderDetailDTO) => void = () => {};
    const call = vi.fn(() => new Promise<AdminOrderDetailDTO>((r) => (resolve = r)));
    let first: Promise<boolean> = Promise.resolve(false);
    let second = true;
    await act(async () => {
      first = result.current.run(call);
      second = await result.current.run(call);
    });
    expect(second).toBe(false);
    expect(result.current.state).toEqual({ kind: "pending" });
    await act(async () => {
      resolve(adminDetailDTO());
      await first;
    });
    expect(call).toHaveBeenCalledTimes(1);
  });

  it("a 409 refusal shows safe copy and re-reads; CSRF does not re-read", async () => {
    const { result, invalidate } = setup();
    const refusal = { kind: "http" as const, status: 409, code: "INVALID_STATE_TRANSITION", message: "RAW", raw: { reason: "not_a_legal_edge" } };
    await act(async () => {
      await result.current.run(() => Promise.reject(refusal));
    });
    expect(result.current.state).toEqual({ kind: "error", message: "That step isn't allowed from the line's current state." });
    expect(invalidate).toHaveBeenCalledTimes(1);

    const csrf = { kind: "http" as const, status: 403, code: "CSRF_INVALID", message: "RAW", raw: {} };
    await act(async () => {
      await result.current.run(() => Promise.reject(csrf));
    });
    expect(result.current.state).toEqual({ kind: "error", message: ADMIN_ORDER_MESSAGES.csrf });
    expect(invalidate).toHaveBeenCalledTimes(1);
  });
});
