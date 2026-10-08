"use client";

import { useState } from "react";

export interface UseCheckoutAttemptResult {
  attemptKey: string;
  startNewAttempt: () => void;
}

// #SECURITY-CHECKOUT-IDEMPOTENCY
//
// `attemptKey` is generated exactly once via React's lazy useState
// initializer — it runs on mount only, never on a subsequent render,
// so a retry of the same submission (a re-render, a resubmit click)
// automatically reuses the same key with no extra bookkeeping.
// `startNewAttempt()` is the ONE explicit, caller-driven way to retire
// the current key and mint a new one — never called automatically by
// this hook. Attempt-key generation is deliberately separate from any
// request/header mapping: this file never references a backend
// header or body field name — a future adapter (blocked on the
// backend contract, FVS-026-IMPLEMENTATION-PLAN.md T08) maps
// `attemptKey` onto whatever the backend confirms.
export function useCheckoutAttempt(): UseCheckoutAttemptResult {
  const [attemptKey, setAttemptKey] = useState(() => crypto.randomUUID());

  function startNewAttempt() {
    setAttemptKey(crypto.randomUUID());
  }

  return { attemptKey, startNewAttempt };
}
