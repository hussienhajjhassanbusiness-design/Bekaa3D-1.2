"use client";

import { useState } from "react";

export interface UseIdempotencyAttemptResult {
  attemptKey: string;
  startNewAttempt: () => void;
}

// #SECURITY-CHECKOUT-IDEMPOTENCY (shared)
//
// Extracted from useCheckoutAttempt.ts (FVS-026), which was already
// fully domain-free in implementation — only its name/location were
// checkout-specific. `attemptKey` is generated exactly once via
// React's lazy useState initializer — it runs on mount only, never
// on a subsequent render, so a retry of the same submission (a
// re-render, a resubmit click) automatically reuses the same key with
// no extra bookkeeping. `startNewAttempt()` is the ONE explicit,
// caller-driven way to retire the current key and mint a new one —
// never called automatically by this hook. Attempt-key generation is
// deliberately separate from any request/header mapping: this file
// never references a backend header or body field name — a future
// adapter (blocked on each consuming slice's own backend contract)
// maps `attemptKey` onto whatever the backend confirms.
export function useIdempotencyAttempt(): UseIdempotencyAttemptResult {
  const [attemptKey, setAttemptKey] = useState(() => crypto.randomUUID());

  function startNewAttempt() {
    setAttemptKey(crypto.randomUUID());
  }

  return { attemptKey, startNewAttempt };
}
