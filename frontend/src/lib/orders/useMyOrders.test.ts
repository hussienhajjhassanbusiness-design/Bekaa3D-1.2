import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { ordersApi } from "./ordersApi";
import { ORDER_HISTORY_PAGE_SIZE, useMyOrder, useMyOrders } from "./useMyOrders";
import { orderKeys } from "./orderKeys";
import { clearUserScopedQueries } from "@/lib/auth/userScopedQueries";
import { detailDTO, ORDER_ID, pageDTO, summaryDTO } from "./orderFixtures";

function setup() {
  const queryClient = new QueryClient();
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
  return { queryClient, wrapper };
}

afterEach(() => {
  vi.restoreAllMocks();
});

const NOT_FOUND = { kind: "http" as const, status: 404, code: "NOT_FOUND", message: "x", raw: {} };

describe("useMyOrders", () => {
  it("requests the first page with no cursor and the page size", async () => {
    const spy = vi.spyOn(ordersApi, "listMyOrders").mockResolvedValue(pageDTO([summaryDTO()]));
    const { wrapper } = setup();
    const { result } = renderHook(() => useMyOrders(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith({ limit: ORDER_HISTORY_PAGE_SIZE, cursor: undefined });
    expect(result.current.hasNextPage).toBe(false);
  });

  it("pages forward with the server's next_cursor", async () => {
    const spy = vi
      .spyOn(ordersApi, "listMyOrders")
      .mockResolvedValueOnce(pageDTO([summaryDTO()], "cursor-2"))
      .mockResolvedValueOnce(pageDTO([summaryDTO({ id: "other" })], null));
    const { wrapper } = setup();
    const { result } = renderHook(() => useMyOrders(), { wrapper });
    await waitFor(() => expect(result.current.hasNextPage).toBe(true));
    await act(async () => {
      await result.current.fetchNextPage();
    });
    expect(spy).toHaveBeenLastCalledWith({ limit: ORDER_HISTORY_PAGE_SIZE, cursor: "cursor-2" });
    await waitFor(() => expect(result.current.data?.pages).toHaveLength(2));
    expect(result.current.hasNextPage).toBe(false);
  });
});

describe("useMyOrder", () => {
  it("reads the order by id under orderKeys.detail", async () => {
    vi.spyOn(ordersApi, "getMyOrder").mockResolvedValue(detailDTO());
    const { wrapper, queryClient } = setup();
    const { result } = renderHook(() => useMyOrder(ORDER_ID), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(queryClient.getQueryData(orderKeys.detail(ORDER_ID))).toEqual(detailDTO());
  });

  it("never retries a 404 (unknown or another customer's order)", async () => {
    const spy = vi.spyOn(ordersApi, "getMyOrder").mockRejectedValue(NOT_FOUND);
    const { wrapper } = setup();
    const { result } = renderHook(() => useMyOrder(ORDER_ID), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("does not fetch when disabled", () => {
    const spy = vi.spyOn(ordersApi, "getMyOrder");
    const { wrapper } = setup();
    renderHook(() => useMyOrder("not-a-uuid", { enabled: false }), { wrapper });
    expect(spy).not.toHaveBeenCalled();
  });
});

describe("logout / user switch", () => {
  it("clearUserScopedQueries drops every cached order list and detail", async () => {
    vi.spyOn(ordersApi, "getMyOrder").mockResolvedValue(detailDTO());
    vi.spyOn(ordersApi, "listMyOrders").mockResolvedValue(pageDTO([summaryDTO()]));
    const { wrapper, queryClient } = setup();
    const detail = renderHook(() => useMyOrder(ORDER_ID), { wrapper });
    const list = renderHook(() => useMyOrders(), { wrapper });
    await waitFor(() => expect(detail.result.current.isSuccess && list.result.current.isSuccess).toBe(true));
    detail.unmount();
    list.unmount();

    clearUserScopedQueries(queryClient);

    expect(queryClient.getQueriesData({ queryKey: orderKeys.root })).toEqual([]);
  });
});
