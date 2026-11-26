// FVS-003-IMPLEMENTATION-PLAN.md §7 (corrected, BATCH 2) — a fully generic
// async single-flight / call-deduplication primitive. Deliberately has NO
// knowledge of refresh, apiClient, HTTP, cookies, CSRF, or auth state —
// wiring it to a real refresh call is a separate, later, contract-blocked
// task (T07). This module imports nothing beyond its own type.
//
// Only deduplicates simultaneous execution: no retry, no backoff, no error
// inspection, no boolean-collapsing of the result — the wrapped function's
// real resolve value or rejection reason always passes through unchanged.
export function createSingleFlight<T>(fn: () => Promise<T>): () => Promise<T> {
  let inFlight: Promise<T> | null = null;

  return function runSingleFlight(): Promise<T> {
    if (inFlight) {
      return inFlight;
    }

    // `fn()` is called synchronously, within this same call — a concurrent
    // caller arriving before the current microtask queue drains must still
    // see `inFlight` already set. A synchronous throw (not every caller
    // returns a Promise defensively) is caught here and converted into a
    // rejected promise, so it settles through the exact same `.finally()`
    // path as any async failure instead of leaving the primitive stuck.
    let result: Promise<T>;
    try {
      result = fn();
    } catch (error) {
      result = Promise.reject(error);
    }

    inFlight = result.finally(() => {
      inFlight = null;
    });

    return inFlight;
  };
}
