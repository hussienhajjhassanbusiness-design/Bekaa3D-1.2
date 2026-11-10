import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { cartKeys } from "@/lib/cart/cartKeys";
import { checkoutApi } from "./checkoutApi";
import { usePlaceOrder } from "./usePlaceOrder";
import type { CheckoutReadDTO, CheckoutRequestDTO } from "./checkoutTypes";

// Success: the server has cleared the cart, so the canonical cart family
// (shared by /cart, the header count and /checkout) is invalidated, never
// patched with a guessed empty cart. Failure: nothing is invalidated here
// (the page decides from the typed outcome) and nothing is retried.

function setup() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
  return { invalidateSpy, wrapper };
}

afterEach(() => vi.restoreAllMocks());

const BODY: CheckoutRequestDTO = {
  payment_method: "online",
  accept_terms: true,
};
const READ = {
  order: { id: "o-1" },
  payment: null,
  dropped_lines: [],
} as unknown as CheckoutReadDTO;

describe("usePlaceOrder", () => {
  it("passes the body and the key through and invalidates the cart family on success", async () => {
    const spy = vi.spyOn(checkoutApi, "placeOrder").mockResolvedValue(READ);
    const { invalidateSpy, wrapper } = setup();
    const { result } = renderHook(() => usePlaceOrder(), { wrapper });
    await act(async () => {
      await expect(
        result.current.mutateAsync({
          body: BODY,
          idempotencyKey: "key-12345678",
        })
      ).resolves.toBe(READ);
    });
    expect(spy).toHaveBeenCalledWith(BODY, "key-12345678");
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: cartKeys.root });
  });

  it("a failure is surfaced once, never retried, and does not touch the cart cache", async () => {
    const error = { kind: "network", message: "x", raw: undefined };
    const spy = vi.spyOn(checkoutApi, "placeOrder").mockRejectedValue(error);
    const { invalidateSpy, wrapper } = setup();
    const { result } = renderHook(() => usePlaceOrder(), { wrapper });
    await act(async () => {
      await expect(
        result.current.mutateAsync({
          body: BODY,
          idempotencyKey: "key-12345678",
        })
      ).rejects.toBe(error);
    });
    expect(spy).toHaveBeenCalledTimes(1);
    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});
