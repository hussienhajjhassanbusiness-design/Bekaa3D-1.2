import { describe, it, expect, vi, afterEach } from "vitest";
import { apiClient } from "@/lib/api/apiClient";
import { refreshSession } from "@/lib/auth/refreshSession";
import { CHECKOUT_TIMEOUT_MS, checkoutApi } from "./checkoutApi";
import type { CheckoutReadDTO, CheckoutRequestDTO } from "./checkoutTypes";

// POST /api/v1/checkout (backend 2dfb27b): verified session, X-CSRF-Token,
// required Idempotency-Key header, 201 CheckoutRead.

vi.mock("@/lib/auth/refreshSession", () => ({ refreshSession: vi.fn() }));
const mockedRefreshSession = vi.mocked(refreshSession);

afterEach(() => {
  vi.restoreAllMocks();
});

const BODY: CheckoutRequestDTO = {
  payment_method: "online",
  accept_terms: true,
  accept_digital_final_sale: true,
};
const READ = {
  order: { id: "o-1" },
  payment: null,
  dropped_lines: [],
} as unknown as CheckoutReadDTO;
const AUTH_REQUIRED = {
  kind: "http" as const,
  status: 401,
  code: "AUTH_REQUIRED",
  message: "x",
  raw: {},
};

describe("checkoutApi.placeOrder", () => {
  it("POSTs the exact body to /api/v1/checkout with CSRF and the Idempotency-Key header", async () => {
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(READ);
    await expect(checkoutApi.placeOrder(BODY, "key-abc-123")).resolves.toBe(READ);
    expect(postSpy).toHaveBeenCalledTimes(1);
    expect(postSpy).toHaveBeenCalledWith("/api/v1/checkout", BODY, {
      csrf: true,
      headers: { "Idempotency-Key": "key-abc-123" },
      timeoutMs: CHECKOUT_TIMEOUT_MS,
    });
  });

  it("allows longer than the provider's own 10 s call before giving up", () => {
    expect(CHECKOUT_TIMEOUT_MS).toBeGreaterThan(10_000);
  });

  it("after a silent session refresh, retries ONCE with the SAME key and the SAME body", async () => {
    const postSpy = vi.spyOn(apiClient, "post").mockRejectedValueOnce(AUTH_REQUIRED).mockResolvedValueOnce(READ);
    mockedRefreshSession.mockResolvedValue(true);
    await expect(checkoutApi.placeOrder(BODY, "key-abc-123")).resolves.toBe(READ);
    expect(postSpy).toHaveBeenCalledTimes(2);
    expect(postSpy.mock.calls[1]).toEqual(postSpy.mock.calls[0]);
  });

  it("a failed refresh surfaces the original AUTH_REQUIRED and sends nothing more", async () => {
    const postSpy = vi.spyOn(apiClient, "post").mockRejectedValue(AUTH_REQUIRED);
    mockedRefreshSession.mockResolvedValue(false);
    await expect(checkoutApi.placeOrder(BODY, "key-abc-123")).rejects.toBe(AUTH_REQUIRED);
    expect(postSpy).toHaveBeenCalledTimes(1);
  });

  it("never retries any other failure by itself", async () => {
    const conflict = {
      kind: "http" as const,
      status: 409,
      code: "CART_PRICE_CHANGED",
      message: "x",
      raw: {},
    };
    const postSpy = vi.spyOn(apiClient, "post").mockRejectedValue(conflict);
    await expect(checkoutApi.placeOrder(BODY, "key-abc-123")).rejects.toBe(conflict);
    expect(postSpy).toHaveBeenCalledTimes(1);
    expect(mockedRefreshSession).not.toHaveBeenCalled();
  });
});
