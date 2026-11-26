import { describe, it, expect, vi, afterEach } from "vitest";
import { apiClient } from "@/lib/api/apiClient";
import { refreshSession } from "@/lib/auth/refreshSession";
import { cartApi } from "./cartApi";
import type { CartReadDTO } from "./cartTypes";

// The four built cart operations (openapi.json, backend 2dfb27b
// src/app/ordering/api/cart.py). GET needs a session; every write needs a
// verified email and the double-submit CSRF header. There is no clear-cart
// route: checkout clears the cart server-side.

vi.mock("@/lib/auth/refreshSession", () => ({ refreshSession: vi.fn() }));
const mockedRefreshSession = vi.mocked(refreshSession);

afterEach(() => {
  vi.restoreAllMocks();
});

const EMPTY: CartReadDTO = { id: null, items: [], contains_physical: false, contains_digital: false, updated_at: null };
const AUTH_REQUIRED = { kind: "http" as const, status: 401, code: "AUTH_REQUIRED", message: "x", raw: {} };

describe("cartApi", () => {
  it("getCart: GET /api/v1/cart, no CSRF", async () => {
    const getSpy = vi.spyOn(apiClient, "get").mockResolvedValue(EMPTY);
    await expect(cartApi.getCart()).resolves.toEqual(EMPTY);
    expect(getSpy).toHaveBeenCalledWith("/api/v1/cart");
  });

  it("addItem: POST /api/v1/cart/items with exactly {product_id, quantity} and csrf: true", async () => {
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(EMPTY);
    await cartApi.addItem({ product_id: "p-1", quantity: 2 });
    expect(postSpy).toHaveBeenCalledWith("/api/v1/cart/items", { product_id: "p-1", quantity: 2 }, { csrf: true });
  });

  it("setItemQuantity: PATCH /api/v1/cart/items/{product_id} with exactly {quantity} and csrf: true", async () => {
    const patchSpy = vi.spyOn(apiClient, "patch").mockResolvedValue(EMPTY);
    await cartApi.setItemQuantity("p-1", 3);
    expect(patchSpy).toHaveBeenCalledWith("/api/v1/cart/items/p-1", { quantity: 3 }, { csrf: true });
  });

  it("removeItem: DELETE /api/v1/cart/items/{product_id} with csrf: true", async () => {
    const delSpy = vi.spyOn(apiClient, "del").mockResolvedValue(undefined);
    await cartApi.removeItem("p-1");
    expect(delSpy).toHaveBeenCalledWith("/api/v1/cart/items/p-1", { csrf: true });
  });

  it("URL-encodes the product id in the path", async () => {
    const delSpy = vi.spyOn(apiClient, "del").mockResolvedValue(undefined);
    await cartApi.removeItem("a/b");
    expect(delSpy).toHaveBeenCalledWith("/api/v1/cart/items/a%2Fb", { csrf: true });
  });

  it("exposes no clear-cart operation (the contract has none)", () => {
    expect(Object.keys(cartApi).sort()).toEqual(["addItem", "getCart", "removeItem", "setItemQuantity"]);
  });

  it("refreshes once on 401 AUTH_REQUIRED and retries the write", async () => {
    mockedRefreshSession.mockResolvedValue(true);
    const postSpy = vi.spyOn(apiClient, "post").mockRejectedValueOnce(AUTH_REQUIRED).mockResolvedValueOnce(EMPTY);
    await expect(cartApi.addItem({ product_id: "p-1", quantity: 1 })).resolves.toEqual(EMPTY);
    expect(postSpy).toHaveBeenCalledTimes(2);
    expect(mockedRefreshSession).toHaveBeenCalledTimes(1);
  });

  it("surfaces the original 401 when the refresh fails", async () => {
    mockedRefreshSession.mockResolvedValue(false);
    vi.spyOn(apiClient, "get").mockRejectedValue(AUTH_REQUIRED);
    await expect(cartApi.getCart()).rejects.toEqual(AUTH_REQUIRED);
  });
});
