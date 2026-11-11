"use client";

import { useState } from "react";
import { IDEMPOTENCY_KEY_PATTERN } from "@/lib/checkout/checkoutIdempotency";

// #SECURITY-ADMIN-REFUND-IDEMPOTENCY (phase 5I)
//
// POST /api/v1/admin/orders/{id}/refunds and POST /api/v1/admin/refunds/
// {id}/reissue require an `Idempotency-Key` (^[A-Za-z0-9._:-]{8,255}$; scope
// admin_refund_create / admin_refund_reissue per administrator; "one key per
// intended refund"). Same key + same body replays the stored 201
// (`Idempotent-Replayed: true`); same key + another body is 409
// IDEMPOTENCY_KEY_CONFLICT; a running claim is 409
// IDEMPOTENCY_REQUEST_IN_PROGRESS; every refusal rolls the claim back.
//
// So a key is bound to the exact intended refund (its target and body).
// It is kept only while the outcome is UNCERTAIN (network, timeout, 5xx,
// in progress), so the administrator's resend cannot record a second
// refund; any definitive answer retires it. Memory only, never shown.

export interface RefundAttemptTracker {
  keyFor(fingerprint: string): string;
  retire(): void;
}

export function createRefundAttemptTracker(generate: () => string = () => crypto.randomUUID()): RefundAttemptTracker {
  let current: { fingerprint: string; key: string } | null = null;
  return {
    keyFor(fingerprint) {
      if (current && current.fingerprint === fingerprint) return current.key;
      const key = generate();
      if (!IDEMPOTENCY_KEY_PATTERN.test(key)) throw new Error("refund idempotency key does not match the backend pattern");
      current = { fingerprint, key };
      return key;
    },
    retire() {
      current = null;
    },
  };
}

export function useRefundAttemptTracker(): RefundAttemptTracker {
  const [tracker] = useState(() => createRefundAttemptTracker());
  return tracker;
}
