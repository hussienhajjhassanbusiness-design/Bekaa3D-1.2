import { apiClient } from "@/lib/api/apiClient";
import { authenticatedRequest } from "@/lib/auth/authenticatedRequest";
import type { CheckoutReadDTO, CheckoutRequestDTO } from "./checkoutTypes";

// #ARCHITECTURE-CHECKOUT-API
//
// POST /api/v1/checkout (backend 2dfb27b ordering/api/checkout.py):
// verified customer session, the double-submit X-CSRF-Token, and the
// required `Idempotency-Key` header (see checkoutIdempotency.ts). 201
// returns a CheckoutRead. The key and body are captured once in the call
// closure, so the shared refresh-on-401-then-retry-once wrapper can only
// ever resend the identical request, which the server treats as the same
// checkout. No other automatic retry exists.
const PATH = "/api/v1/checkout";

// The online leg calls the payment provider (10 s server-side timeout)
// between two transactions, so the client waits longer than its 10 s
// default before calling the outcome unknown.
export const CHECKOUT_TIMEOUT_MS = 30_000;

function placeOrder(body: CheckoutRequestDTO, idempotencyKey: string): Promise<CheckoutReadDTO> {
  return authenticatedRequest(() =>
    apiClient.post<CheckoutReadDTO>(PATH, body, {
      csrf: true,
      headers: { "Idempotency-Key": idempotencyKey },
      timeoutMs: CHECKOUT_TIMEOUT_MS,
    })
  );
}

export const checkoutApi = { placeOrder };
