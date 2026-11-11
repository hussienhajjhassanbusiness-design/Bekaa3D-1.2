import { describe, it, expect, vi, afterEach } from "vitest";
import { apiClient } from "@/lib/api/apiClient";
import { refreshSession } from "@/lib/auth/refreshSession";
import { buildOrdersSearchParams, ordersApi } from "./ordersApi";
import { orderKeys } from "./orderKeys";
import { classifyOrderError } from "./orderErrors";
import { ORDER_ID } from "./orderFixtures";

vi.mock("@/lib/auth/refreshSession", () => ({ refreshSession: vi.fn() }));
const mockedRefreshSession = vi.mocked(refreshSession);

afterEach(() => {
  vi.restoreAllMocks();
  mockedRefreshSession.mockReset();
});

const AUTH_REQUIRED = { kind: "http" as const, status: 401, code: "AUTH_REQUIRED", message: "x", raw: {} };

describe("buildOrdersSearchParams", () => {
  it("is empty for no params and passes cursor/limit through unchanged", () => {
    expect(buildOrdersSearchParams({}).toString()).toBe("");
    const search = buildOrdersSearchParams({ cursor: "opaque==", limit: 20 });
    expect(search.get("cursor")).toBe("opaque==");
    expect(search.get("limit")).toBe("20");
  });
});

describe("ordersApi", () => {
  it("lists via GET /api/v1/me/orders with the querystring", async () => {
    const getSpy = vi.spyOn(apiClient, "get").mockResolvedValue({ items: [], next_cursor: null });
    await ordersApi.listMyOrders({ limit: 20, cursor: "c2" });
    expect(getSpy).toHaveBeenCalledWith("/api/v1/me/orders?cursor=c2&limit=20");
  });

  it("lists via the bare path with no params", async () => {
    const getSpy = vi.spyOn(apiClient, "get").mockResolvedValue({ items: [], next_cursor: null });
    await ordersApi.listMyOrders();
    expect(getSpy).toHaveBeenCalledWith("/api/v1/me/orders");
  });

  it("reads one order via GET /api/v1/me/orders/{id}, encoding the id", async () => {
    const getSpy = vi.spyOn(apiClient, "get").mockResolvedValue({});
    await ordersApi.getMyOrder(ORDER_ID);
    expect(getSpy).toHaveBeenCalledWith(`/api/v1/me/orders/${ORDER_ID}`);
    await ordersApi.getMyOrder("a/b");
    expect(getSpy).toHaveBeenLastCalledWith("/api/v1/me/orders/a%2Fb");
  });

  it("refreshes the session once on 401 AUTH_REQUIRED, then retries", async () => {
    mockedRefreshSession.mockResolvedValue(true);
    const getSpy = vi
      .spyOn(apiClient, "get")
      .mockRejectedValueOnce(AUTH_REQUIRED)
      .mockResolvedValueOnce({ items: [], next_cursor: null });
    await expect(ordersApi.listMyOrders()).resolves.toEqual({ items: [], next_cursor: null });
    expect(mockedRefreshSession).toHaveBeenCalledTimes(1);
    expect(getSpy).toHaveBeenCalledTimes(2);
  });

  it("surfaces the original AUTH_REQUIRED when refresh fails (session expired)", async () => {
    mockedRefreshSession.mockResolvedValue(false);
    vi.spyOn(apiClient, "get").mockRejectedValue(AUTH_REQUIRED);
    await expect(ordersApi.getMyOrder(ORDER_ID)).rejects.toBe(AUTH_REQUIRED);
  });
});

describe("orderKeys", () => {
  it("hangs every key off the one user-scoped root", () => {
    expect(orderKeys.root).toEqual(["orders"]);
    expect(orderKeys.list({ limit: 20 })).toEqual(["orders", "list", { limit: 20 }]);
    expect(orderKeys.detail(ORDER_ID)).toEqual(["orders", "detail", ORDER_ID]);
    expect(orderKeys.list({}).slice(0, 2)).toEqual(orderKeys.lists());
  });
});

describe("classifyOrderError", () => {
  it("maps by status/code only", () => {
    expect(classifyOrderError({ kind: "http", status: 404, code: "NOT_FOUND", message: "", raw: {} })).toBe("not-found");
    expect(classifyOrderError({ kind: "http", status: 422, code: "VALIDATION_ERROR", message: "", raw: {} })).toBe(
      "not-found"
    );
    expect(classifyOrderError(AUTH_REQUIRED)).toBe("auth");
    expect(classifyOrderError({ kind: "http", status: 500, code: "INTERNAL_ERROR", message: "", raw: {} })).toBe(
      "generic"
    );
    expect(classifyOrderError({ kind: "network", message: "", raw: {} })).toBe("generic");
    expect(classifyOrderError(new Error("boom"))).toBe("generic");
  });
});
