// FVS-003-IMPLEMENTATION-PLAN.md §6/§8 (confirmed BATCH 3A) — the
// refresh-on-401-then-retry-once wrapper for authenticated calls.
//
// Refreshability rule: ONLY `401 AUTH_REQUIRED` is refreshable. Every other
// failure — `401 MFA_REQUIRED`, `403`, `404`, network, timeout, `500`, any
// other code — passes through completely unchanged, never triggering a
// refresh attempt.
//
// Replay safety: the backend has confirmed authenticated write endpoints
// authenticate before their business side effect, so both reads and writes
// may be retried once after a successful refresh — this wrapper makes no
// GET/POST distinction.
//
// Never recursive: this module calls `refreshSession()` (src/lib/auth/
// refreshSession.ts), which itself calls `apiClient` directly — never this
// wrapper. `login`/`logout`/`refresh`/MFA/password-reset endpoints must
// never be called through this wrapper (enforced by call-site architecture,
// not a path blacklist here — see the plan's §6 exclusion rule).
import type { ApiError } from "@/lib/api/ApiError";
import { refreshSession } from "./refreshSession";

function isAuthRequiredError(error: unknown): error is ApiError {
  return (
    typeof error === "object" &&
    error !== null &&
    "kind" in error &&
    (error as ApiError).kind === "http" &&
    (error as ApiError).status === 401 &&
    (error as ApiError).code === "AUTH_REQUIRED"
  );
}

export async function authenticatedRequest<T>(call: () => Promise<T>): Promise<T> {
  try {
    return await call();
  } catch (error) {
    if (!isAuthRequiredError(error)) {
      throw error;
    }

    const refreshed = await refreshSession();
    if (!refreshed) {
      // Surface the ORIGINAL AUTH_REQUIRED error — refresh failing is not a
      // different error for the caller to learn about, and no second
      // refresh is ever attempted.
      throw error;
    }

    // Retry exactly once. Whatever this resolves or rejects with — even
    // another AUTH_REQUIRED — propagates unchanged; no second refresh.
    return await call();
  }
}
