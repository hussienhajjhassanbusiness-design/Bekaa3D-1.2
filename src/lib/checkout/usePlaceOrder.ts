import { useMutation, useQueryClient } from "@tanstack/react-query";
import { cartKeys } from "@/lib/cart/cartKeys";
import { orderKeys } from "@/lib/orders/orderKeys";
import { checkoutApi } from "./checkoutApi";
import type { CheckoutRequestDTO } from "./checkoutTypes";

export interface PlaceOrderInput {
  body: CheckoutRequestDTO;
  idempotencyKey: string;
}

// #ARCHITECTURE-CANONICAL-CART-QUERY (checkout side)
//
// A placed order means the server cleared the cart in the same
// transaction, so the one canonical cart family is invalidated (the /cart
// page, the header count and /checkout all re-read it). Failures are left
// to the page, which branches on the typed outcome (checkoutErrors.ts) and
// invalidates only what that outcome says changed. Never retried: a retry
// is always an explicit customer action with the same key.
//
// Phase 5E: the new order also changes the customer's order history, so
// the canonical order family is invalidated too (#ARCHITECTURE-CANONICAL-
// ORDERS-QUERY).
export function usePlaceOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ body, idempotencyKey }: PlaceOrderInput) => checkoutApi.placeOrder(body, idempotencyKey),
    retry: false,
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: cartKeys.root }),
        queryClient.invalidateQueries({ queryKey: orderKeys.root }),
      ]),
  });
}
