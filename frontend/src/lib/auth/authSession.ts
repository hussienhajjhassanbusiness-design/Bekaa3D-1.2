// FVS-003-IMPLEMENTATION-PLAN.md §1/§9/§10 (confirmed BATCH 3A) — the
// backend-approved bootstrap algorithm: a csrf_token-cookie precheck (zero
// network requests for a definitely-anonymous visitor), then GET /api/v1/me,
// with exactly one coordinated refresh + one /me retry on 401 AUTH_REQUIRED.
// Any other outcome resolves anonymous (`null`) — never a false
// "authenticated" result. Calls `apiClient` directly, never through
// `authenticatedRequest` — this IS the bootstrap check, not a request that
// should itself re-enter that generic wrapper.
import { apiClient } from "@/lib/api/apiClient";
import type { ApiError } from "@/lib/api/ApiError";
import { readCsrfToken } from "./csrf";
import { refreshSession } from "./refreshSession";

export const AUTH_SESSION_QUERY_KEY = ["auth", "session"] as const;

// Non-secret metadata only — no token/credential field of any kind.
export interface SafeUser {
  id: string;
  email: string;
  role: string;
  emailVerified: boolean;
  emailVerifiedAt: string | null;
  createdAt: string;
}

interface RawMeResponse {
  id: string;
  email: string;
  role: string;
  email_verified: boolean;
  email_verified_at: string | null;
  created_at: string;
}

function mapRawUser(raw: RawMeResponse): SafeUser {
  return {
    id: raw.id,
    email: raw.email,
    role: raw.role,
    emailVerified: raw.email_verified,
    emailVerifiedAt: raw.email_verified_at,
    createdAt: raw.created_at,
  };
}

function isAuthRequiredError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "kind" in error &&
    (error as ApiError).kind === "http" &&
    (error as ApiError).status === 401 &&
    (error as ApiError).code === "AUTH_REQUIRED"
  );
}

// #ARCHITECTURE-CANONICAL-AUTH-QUERY
// A genuine transport/server failure (network unreachable, our own
// request timeout, an unparseable response, or a 5xx) says NOTHING about
// whether the current session is valid — it must never be collapsed into
// "anonymous," or a customer with a perfectly valid session could be
// bounced to /login by a transient blip (this was a real cross-slice
// defect, found and fixed at FVS-006). Only a definitive 401 (AUTH_REQUIRED
// or any other code — a 401 is still a real "not authenticated" signal
// from the server) and a missing csrf_token cookie are "confirmed
// anonymous" outcomes. Everything else here re-throws so the
// ["auth","session"] query settles into a genuine error state instead,
// which FVS-006's profile page (and any future consumer) surfaces as a
// retryable error rather than a false logout.
function isUnexpectedTransportError(error: unknown): boolean {
  if (typeof error !== "object" || error === null || !("kind" in error)) {
    return true;
  }
  const apiError = error as ApiError;
  if (apiError.kind === "network" || apiError.kind === "timeout" || apiError.kind === "parse") {
    return true;
  }
  return apiError.kind === "http" && apiError.status !== undefined && apiError.status >= 500;
}

async function fetchMe(): Promise<SafeUser> {
  const raw = await apiClient.get<RawMeResponse>("/api/v1/me");
  return mapRawUser(raw);
}

export async function bootstrapAuthSession(): Promise<SafeUser | null> {
  if (readCsrfToken() === undefined) {
    return null;
  }

  try {
    return await fetchMe();
  } catch (error) {
    if (isUnexpectedTransportError(error)) {
      throw error;
    }
    if (!isAuthRequiredError(error)) {
      // A definitive, non-AUTH_REQUIRED 4xx (e.g. an unrecognized 401
      // code such as MFA_REQUIRED) is still a real "not currently
      // authenticated" signal — the safe default stays anonymous, never a
      // false "authenticated."
      return null;
    }

    const refreshed = await refreshSession();
    if (!refreshed) {
      return null;
    }

    try {
      return await fetchMe();
    } catch (retryError) {
      if (isUnexpectedTransportError(retryError)) {
        throw retryError;
      }
      // Bounded: never retry /me a third time, regardless of why the
      // retry failed.
      return null;
    }
  }
}

export function getAuthSessionQueryOptions() {
  return {
    queryKey: AUTH_SESSION_QUERY_KEY,
    queryFn: bootstrapAuthSession,
    // Session validity isn't something that goes stale on a timer — it's
    // invalidated by explicit events (login success, logout, refresh
    // failure), never a background poll.
    staleTime: Infinity,
    // The bootstrap sequence's own internal AUTH_REQUIRED -> refresh ->
    // retry-once logic is bounded application logic inside the queryFn
    // itself, settling exactly once — this is not TanStack's own retry
    // mechanism, which stays disabled.
    retry: false,
  } as const;
}
