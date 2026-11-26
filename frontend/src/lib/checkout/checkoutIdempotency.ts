"use client";

import { useState } from "react";
import type { CheckoutRequestDTO } from "./checkoutTypes";

// #SECURITY-CHECKOUT-IDEMPOTENCY
//
// POST /api/v1/checkout requires an `Idempotency-Key` header (backend
// 2dfb27b, openapi.json; ordering/api/checkout.py; docs/checkout.md):
//   - pattern ^[A-Za-z0-9._:-]{8,255}$, scoped per user, kept 24 h;
//   - "one key per 'Place order' press and all its automatic retries; a new
//     key after any change";
//   - same key + same body replays the stored 201 (or the post-commit 502)
//     with `Idempotent-Replayed: true`; same key + different body is
//     409 IDEMPOTENCY_KEY_CONFLICT; a claim still running is
//     409 IDEMPOTENCY_REQUEST_IN_PROGRESS; every other refusal rolls the
//     claim back (the key is free again).
//
// So a key is bound to the exact body it was minted for. Retrying the same
// body (a timeout, a network drop, a 5xx, an in-progress answer, the
// silent refresh-and-retry in authenticatedRequest) reuses the key, which
// is what makes a retry unable to create a second order. Any change to the
// body mints a new key. The key lives in memory only (component state): it survives
// re-renders, is never rendered, and is never written to storage, so it
// is gone on reload or when the page unmounts.

export const IDEMPOTENCY_KEY_PATTERN = /^[A-Za-z0-9._:-]{8,255}$/;

function stableStringify(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(",")}]`;
  }
  if (value !== null && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([, item]) => item !== undefined)
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
    return `{${entries.map(([key, item]) => `${JSON.stringify(key)}:${stableStringify(item)}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

export function checkoutFingerprint(body: object): string {
  return stableStringify(body);
}

// Generic over the body (phase 6C: offer checkout reuses the same rules
// for POST /me/offers/{id}/checkout); cart checkout keeps the default.
export interface CheckoutAttemptTracker<TBody extends object = CheckoutRequestDTO> {
  // The key for this exact body: the current one if the body is unchanged,
  // otherwise a freshly minted one.
  keyFor(body: TBody): string;
  // Forget the current key (after a placed order, or a key conflict).
  retire(): void;
  currentKey(): string | null;
}

function defaultGenerate(): string {
  return crypto.randomUUID();
}

export function createCheckoutAttemptTracker<TBody extends object = CheckoutRequestDTO>(
  generate: () => string = defaultGenerate
): CheckoutAttemptTracker<TBody> {
  let current: { fingerprint: string; key: string } | null = null;

  return {
    keyFor(body) {
      const fingerprint = checkoutFingerprint(body);
      if (current && current.fingerprint === fingerprint) {
        return current.key;
      }
      const key = generate();
      if (!IDEMPOTENCY_KEY_PATTERN.test(key)) {
        throw new Error("checkout idempotency key does not match the backend pattern");
      }
      current = { fingerprint, key };
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

export function useCheckoutAttemptTracker<TBody extends object = CheckoutRequestDTO>(): CheckoutAttemptTracker<TBody> {
  // The lazy initializer runs once per mount; the tracker object is then
  // stable across every re-render.
  const [tracker] = useState(() => createCheckoutAttemptTracker<TBody>());
  return tracker;
}
