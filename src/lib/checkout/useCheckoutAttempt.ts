"use client";

import { useIdempotencyAttempt, type UseIdempotencyAttemptResult } from "@/lib/shared/useIdempotencyAttempt";

export type UseCheckoutAttemptResult = UseIdempotencyAttemptResult;

// #SECURITY-CHECKOUT-IDEMPOTENCY
//
// Thin wrapper over the shared useIdempotencyAttempt primitive
// (FVS-032-IMPLEMENTATION-PLAN.md T08 extraction) — preserves this
// hook's exact existing name/shape/behavior for every current
// checkout caller; see useIdempotencyAttempt.ts for the actual
// implementation and its documentation.
export function useCheckoutAttempt(): UseCheckoutAttemptResult {
  return useIdempotencyAttempt();
}
