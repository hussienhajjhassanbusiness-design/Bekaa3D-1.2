import { describe, it, expect, vi, afterEach } from "vitest";
import { apiClient } from "@/lib/api/apiClient";
import { refreshSession } from "@/lib/auth/refreshSession";
import { buildOrdersSearchParams, ordersApi, PAYMENT_RETRY_TIMEOUT_MS } from "./ordersApi";
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

describe("ordersApi.retryPayment (FVS-027)", () => {
  const READ = { order: { id: ORDER_ID }, payment: { redirect_url: null } };

  it("POSTs an empty body to /api/v1/me/orders/{id}/payments with CSRF and the Idempotency-Key", async () => {
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(READ);
    await expect(ordersApi.retryPayment(ORDER_ID, "retry-key-0001")).resolves.toBe(READ);
    expect(postSpy).toHaveBeenCalledTimes(1);
    expect(postSpy).toHaveBeenCalledWith(
      `/api/v1/me/orders/${ORDER_ID}/payments`,
      {},
      { csrf: true, headers: { "Idempotency-Key": "retry-key-0001" }, timeoutMs: PAYMENT_RETRY_TIMEOUT_MS }
    );
    // Never a provider, an amount or a total.
    expect(Object.keys(postSpy.mock.calls[0]![1] as object)).toEqual([]);
  });

  it("encodes the id and waits longer than the provider's own 10 s call", async () => {
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(READ);
    await ordersApi.retryPayment("a/b", "retry-key-0001");
    expect(postSpy.mock.calls[0]![0]).toBe("/api/v1/me/orders/a%2Fb/payments");
    expect(PAYMENT_RETRY_TIMEOUT_MS).toBeGreaterThan(10_000);
  });

  it("after a silent session refresh, resends ONCE with the SAME key and body", async () => {
    mockedRefreshSession.mockResolvedValue(true);
    const postSpy = vi.spyOn(apiClient, "post").mockRejectedValueOnce(AUTH_REQUIRED).mockResolvedValueOnce(READ);
    await expect(ordersApi.retryPayment(ORDER_ID, "retry-key-0001")).resolves.toBe(READ);
    expect(postSpy).toHaveBeenCalledTimes(2);
    expect(postSpy.mock.calls[1]).toEqual(postSpy.mock.calls[0]);
  });

  it("never retries any other failure by itself", async () => {
    const conflict = { kind: "http" as const, status: 409, code: "PAYMENT_ALREADY_ACTIVE", message: "x", raw: {} };
    const postSpy = vi.spyOn(apiClient, "post").mockRejectedValue(conflict);
    await expect(ordersApi.retryPayment(ORDER_ID, "retry-key-0001")).rejects.toBe(conflict);
    expect(postSpy).toHaveBeenCalledTimes(1);
    expect(mockedRefreshSession).not.toHaveBeenCalled();
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

describe("ordersApi customer order actions (FVS-031)", () => {
  const DETAIL = { id: ORDER_ID };

  it("cancels via POST /api/v1/me/orders/{id}/cancel with CSRF and no body", async () => {
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(DETAIL);
    await expect(ordersApi.cancelOrder(ORDER_ID)).resolves.toBe(DETAIL);
    expect(postSpy).toHaveBeenCalledWith(`/api/v1/me/orders/${ORDER_ID}/cancel`, undefined, { csrf: true });
  });

  it("confirms receipt via POST /api/v1/me/orders/{id}/confirm-receipt with CSRF and no body", async () => {
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(DETAIL);
    await expect(ordersApi.confirmReceipt(ORDER_ID)).resolves.toBe(DETAIL);
    expect(postSpy).toHaveBeenCalledWith(`/api/v1/me/orders/${ORDER_ID}/confirm-receipt`, undefined, { csrf: true });
  });

  it("reports a problem via POST /api/v1/me/orders/{id}/report-problem with exactly { message }", async () => {
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(DETAIL);
    await expect(ordersApi.reportProblem(ORDER_ID, "The lid is cracked")).resolves.toBe(DETAIL);
    expect(postSpy).toHaveBeenCalledWith(
      `/api/v1/me/orders/${ORDER_ID}/report-problem`,
      { message: "The lid is cracked" },
      { csrf: true }
    );
    expect(Object.keys(postSpy.mock.calls[0]![1] as object)).toEqual(["message"]);
  });

  it("encodes the id on every action path", async () => {
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(DETAIL);
    await ordersApi.cancelOrder("a/b");
    await ordersApi.confirmReceipt("a/b");
    await ordersApi.reportProblem("a/b", "x");
    expect(postSpy.mock.calls.map((call) => call[0])).toEqual([
      "/api/v1/me/orders/a%2Fb/cancel",
      "/api/v1/me/orders/a%2Fb/confirm-receipt",
      "/api/v1/me/orders/a%2Fb/report-problem",
    ]);
  });

  it("after a silent session refresh, resends each action ONCE with the same request", async () => {
    mockedRefreshSession.mockResolvedValue(true);
    const postSpy = vi.spyOn(apiClient, "post").mockRejectedValueOnce(AUTH_REQUIRED).mockResolvedValueOnce(DETAIL);
    await expect(ordersApi.reportProblem(ORDER_ID, "msg")).resolves.toBe(DETAIL);
    expect(postSpy).toHaveBeenCalledTimes(2);
    expect(postSpy.mock.calls[1]).toEqual(postSpy.mock.calls[0]);
  });

  it("never retries a refusal by itself", async () => {
    const refused = { kind: "http" as const, status: 409, code: "ORDER_NOT_CANCELLABLE", message: "x", raw: {} };
    const postSpy = vi.spyOn(apiClient, "post").mockRejectedValue(refused);
    await expect(ordersApi.cancelOrder(ORDER_ID)).rejects.toBe(refused);
    expect(postSpy).toHaveBeenCalledTimes(1);
    expect(mockedRefreshSession).not.toHaveBeenCalled();
  });
});
