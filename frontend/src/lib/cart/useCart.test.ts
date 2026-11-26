import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { cartApi } from "./cartApi";
import { cartKeys } from "./cartKeys";
import { useAddToCart, useCart, useRemoveCartItem, useSetCartItemQuantity } from "./useCart";
import type { CartLineReadDTO, CartReadDTO } from "./cartTypes";

// #ARCHITECTURE-CANONICAL-CART-QUERY — one query per signed-in user.
// Writes are not optimistic: add/PATCH responses (a full CartRead) are
// written into the canonical key verbatim and then the cart family is
// invalidated, so the UI always ends on a fresh server read. DELETE (204)
// only invalidates. Writes are never retried automatically.

vi.mock("@/lib/auth/AuthProvider", () => ({ useAuth: vi.fn() }));
import { useAuth } from "@/lib/auth/AuthProvider";
const mockedUseAuth = vi.mocked(useAuth);

function signedInAs(id: string | null) {
  mockedUseAuth.mockReturnValue({
    user: id ? { id, email: "a@b.c", role: "customer", emailVerified: true, emailVerifiedAt: null, createdAt: "" } : null,
    isAuthenticated: id !== null,
    isLoading: false,
    isError: false,
    logout: vi.fn(),
  } as unknown as ReturnType<typeof useAuth>);
}

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
  return { queryClient, invalidateSpy, wrapper };
}

afterEach(() => {
  vi.restoreAllMocks();
});

const LINE: CartLineReadDTO = {
  product_id: "p-1",
  product_type: "physical",
  name: "Dragon",
  slug: "dragon",
  cover_image: null,
  quantity: 2,
  snapshot_price: { amount_cents: 2500, currency: "USD" },
  current_price: { amount_cents: 2500, currency: "USD" },
  price_changed: false,
  max_quantity: 5,
  over_cap: false,
  purchasable: true,
  unpurchasable_reason: null,
};
const CART: CartReadDTO = {
  id: "c-1",
  items: [LINE],
  contains_physical: true,
  contains_digital: false,
  updated_at: "2026-11-11T10:00:00Z",
};
const NOT_FOUND = { kind: "http" as const, status: 404, code: "NOT_FOUND", message: "x", raw: {} };
const CSRF_INVALID = { kind: "http" as const, status: 403, code: "CSRF_INVALID", message: "x", raw: {} };

describe("useCart", () => {
  it("reads GET /cart into the current user's canonical key and adapts it", async () => {
    signedInAs("u-1");
    vi.spyOn(cartApi, "getCart").mockResolvedValue(CART);
    const { wrapper, queryClient } = setup();
    const { result } = renderHook(() => useCart(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.lines[0]?.productId).toBe("p-1");
    expect(queryClient.getQueryData(cartKeys.current("u-1"))).toEqual(CART);
  });

  it("never requests the cart for an anonymous visitor", async () => {
    signedInAs(null);
    const getSpy = vi.spyOn(cartApi, "getCart").mockResolvedValue(CART);
    const { wrapper } = setup();
    const { result } = renderHook(() => useCart(), { wrapper });

    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(getSpy).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("does not show user A's cached cart to user B", async () => {
    signedInAs("u-1");
    const { wrapper, queryClient } = setup();
    queryClient.setQueryData(cartKeys.current("u-1"), CART);
    signedInAs("u-2");
    const empty: CartReadDTO = { id: null, items: [], contains_physical: false, contains_digital: false, updated_at: null };
    let resolveB: (value: CartReadDTO) => void = () => {};
    vi.spyOn(cartApi, "getCart").mockReturnValue(new Promise((resolve) => (resolveB = resolve)));
    const { result } = renderHook(() => useCart(), { wrapper });

    expect(result.current.data).toBeUndefined();
    await act(async () => resolveB(empty));
    await waitFor(() => expect(result.current.data?.lines).toEqual([]));
  });
});

describe("cart mutations", () => {
  it("add sends the exact CartItemAdd body, writes the returned CartRead, then invalidates the cart family", async () => {
    signedInAs("u-1");
    const addSpy = vi.spyOn(cartApi, "addItem").mockResolvedValue(CART);
    vi.spyOn(cartApi, "getCart").mockResolvedValue(CART);
    const { wrapper, queryClient, invalidateSpy } = setup();
    const { result } = renderHook(() => useAddToCart(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ productId: "p-1", quantity: 2 });
    });

    expect(addSpy).toHaveBeenCalledWith({ product_id: "p-1", quantity: 2 });
    expect(queryClient.getQueryData(cartKeys.current("u-1"))).toEqual(CART);
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: cartKeys.root });
  });

  it("set-quantity sends the product id and the absolute quantity, then adopts the server's CartRead", async () => {
    signedInAs("u-1");
    const serverSaid = { ...CART, items: [{ ...LINE, quantity: 4 }] };
    const patchSpy = vi.spyOn(cartApi, "setItemQuantity").mockResolvedValue(serverSaid);
    vi.spyOn(cartApi, "getCart").mockResolvedValue(serverSaid);
    const { wrapper, queryClient, invalidateSpy } = setup();
    queryClient.setQueryData(cartKeys.current("u-1"), CART);
    const { result } = renderHook(() => useSetCartItemQuantity(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ productId: "p-1", quantity: 4 });
    });

    expect(patchSpy).toHaveBeenCalledWith("p-1", 4);
    expect(queryClient.getQueryData<CartReadDTO>(cartKeys.current("u-1"))?.items[0]?.quantity).toBe(4);
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: cartKeys.root });
  });

  it("set-quantity is not optimistic: the cache is unchanged while the request is pending", async () => {
    signedInAs("u-1");
    let resolvePatch: (value: CartReadDTO) => void = () => {};
    vi.spyOn(cartApi, "setItemQuantity").mockReturnValue(new Promise((resolve) => (resolvePatch = resolve)));
    vi.spyOn(cartApi, "getCart").mockResolvedValue(CART);
    const { wrapper, queryClient } = setup();
    queryClient.setQueryData(cartKeys.current("u-1"), CART);
    const { result } = renderHook(() => useSetCartItemQuantity(), { wrapper });

    act(() => {
      result.current.mutate({ productId: "p-1", quantity: 5 });
    });
    await waitFor(() => expect(result.current.isPending).toBe(true));
    expect(queryClient.getQueryData<CartReadDTO>(cartKeys.current("u-1"))?.items[0]?.quantity).toBe(2);
    await act(async () => resolvePatch(CART));
  });

  it("remove calls DELETE for the product id and invalidates (204 has no body to adopt)", async () => {
    signedInAs("u-1");
    const delSpy = vi.spyOn(cartApi, "removeItem").mockResolvedValue(undefined);
    vi.spyOn(cartApi, "getCart").mockResolvedValue(CART);
    const { wrapper, invalidateSpy } = setup();
    const { result } = renderHook(() => useRemoveCartItem(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ productId: "p-1" });
    });

    expect(delSpy).toHaveBeenCalledWith("p-1");
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: cartKeys.root });
  });

  it("a failed write that changes what the cart shows (404) refetches the cart", async () => {
    signedInAs("u-1");
    vi.spyOn(cartApi, "removeItem").mockRejectedValue(NOT_FOUND);
    vi.spyOn(cartApi, "getCart").mockResolvedValue(CART);
    const { wrapper, invalidateSpy } = setup();
    const { result } = renderHook(() => useRemoveCartItem(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ productId: "p-1" }).catch(() => undefined);
    });

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: cartKeys.root });
  });

  it("a CSRF failure does not refetch and is never retried", async () => {
    signedInAs("u-1");
    const addSpy = vi.spyOn(cartApi, "addItem").mockRejectedValue(CSRF_INVALID);
    const { wrapper, invalidateSpy } = setup();
    const { result } = renderHook(() => useAddToCart(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ productId: "p-1", quantity: 1 }).catch(() => undefined);
    });

    expect(addSpy).toHaveBeenCalledTimes(1);
    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});
