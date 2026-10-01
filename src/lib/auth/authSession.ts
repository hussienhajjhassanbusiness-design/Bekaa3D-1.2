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
    if (!isAuthRequiredError(error)) {
      // Any unexpected failure (network, timeout, 500, a 401 with a
      // different/missing code such as MFA_REQUIRED) resolves anonymous as
      // the safe default — never a false "authenticated."
      return null;
    }

    const refreshed = await refreshSession();
    if (!refreshed) {
      return null;
    }

    try {
      return await fetchMe();
    } catch {
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
