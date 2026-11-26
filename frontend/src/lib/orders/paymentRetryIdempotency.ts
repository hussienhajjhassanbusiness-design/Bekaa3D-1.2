"use client";

import { useState } from "react";
import { IDEMPOTENCY_KEY_PATTERN } from "@/lib/checkout/checkoutIdempotency";

// #SECURITY-PAYMENT-RETRY-IDEMPOTENCY (FVS-027, phase 5F)
//
// POST /api/v1/me/orders/{order_id}/payments requires an `Idempotency-Key`
// (backend 2dfb27b ordering/api/payment_retry.py; docs/payment-recovery.md):
//   - pattern ^[A-Za-z0-9._:-]{8,255}$; scope `payment_retry:{order_id}`
//     per user; kept 24 h;
//   - "one Idempotency-Key is one retry of one order by one user";
//   - the 201 and the 502 PAYMENT_PROVIDER_UNAVAILABLE are replayed for the
//     same key (`Idempotent-Replayed: true`); a running claim is
//     409 IDEMPOTENCY_REQUEST_IN_PROGRESS (`Retry-After: 2`); a different
//     body under the key is 409 IDEMPOTENCY_KEY_CONFLICT; every refusal
//     rolls the claim back.
//
// The body is always `{}`, so a logical attempt is "one press of Retry
// payment for this order". That attempt keeps its key while its outcome is
// UNCERTAIN (network failure, timeout, a 5xx other than the 502, an
// in-progress claim; the silent refresh-and-retry in authenticatedRequest
// resends inside the same call), so a resend can never start a second
// attempt. Any definitive answer (201, 502, a refusal) retires it: the
// customer's next press is a genuinely new attempt with a new key. The key
// is never checkout's (a separate tracker, a separate scope), never shown,
// and lives in memory only: it is gone on reload or unmount.

export interface PaymentRetryTracker {
  // The open attempt's key for this order, or a freshly minted one.
  keyFor(orderId: string): string;
  // A definitive answer arrived: the next press is a new attempt.
  retire(): void;
  currentKey(): string | null;
}

function defaultGenerate(): string {
  return crypto.randomUUID();
}

export function createPaymentRetryTracker(generate: () => string = defaultGenerate): PaymentRetryTracker {
  let current: { orderId: string; key: string } | null = null;

  return {
    keyFor(orderId) {
      if (current && current.orderId === orderId) {
        return current.key;
      }
      const key = generate();
      if (!IDEMPOTENCY_KEY_PATTERN.test(key)) {
        throw new Error("payment retry idempotency key does not match the backend pattern");
      }
      current = { orderId, key };
      return key;
    },
    retire() {
      current = null;
    },
    currentKey() {
      return current?.key ?? null;
    },
  };
}

export function usePaymentRetryTracker(): PaymentRetryTracker {
  const [tracker] = useState(() => createPaymentRetryTracker());
  return tracker;
}
