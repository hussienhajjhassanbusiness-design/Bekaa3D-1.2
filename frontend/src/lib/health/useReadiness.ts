import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/apiClient";
import type { ApiError } from "@/lib/api/ApiError";

// FRONTEND-VERTICAL-SLICE-PLAN.md §16 — only the four states the state
// matrix defines. Never invent "degraded"/"offline"/"starting"/"healthy".
export type ReadinessState = "ready" | "not-ready" | "unreachable" | "timeout";

export interface UseReadinessResult {
  // undefined only during the initial load (no result has ever arrived
  // yet) — never conflated with a settled "not-ready" outcome. See
  // isLoading below, which callers should check first.
  state: ReadinessState | undefined;
  // TanStack's own isLoading (== isFetching && isPending): true only
  // during the very first check. Background refetches after that do not
  // flip this back to true — §16's own "LoadingSpinner shown only during
  // the first check" requirement, satisfied by using TanStack's existing
  // isLoading/isFetching distinction rather than inventing one.
  isLoading: boolean;
}

const READINESS_QUERY_KEY = ["health", "ready"] as const;

// Exported primarily for testability: proves the production hook is
// configured with the approved bounded settings via a plain object
// assertion, without needing to intercept TanStack's own ESM export (which
// Vitest cannot redefine — its module namespace is non-configurable).
export function getReadinessQueryOptions() {
  return {
    queryKey: READINESS_QUERY_KEY,
    // §16: apiClient.get("/api/health/ready") only — never /health/ready
    // directly (T09 restricts apiClient to same-origin /api/... paths;
    // T10's rewrite forwards this to the real backend's GET /health/ready)
    // and never /health/live or /api/health/live (§16: not used by this
    // slice — no UI need exists yet for a liveness-only signal).
    //
    // TanStack Query does not allow a query function to resolve
    // `undefined` ("Query data cannot be undefined") — but apiClient
    // deliberately resolves `undefined` on a 2xx response with an
    // empty/unparseable body (§13 point 6, T09's own committed contract,
    // unchanged here). The `?? null` below is a narrow, T13a-local
    // adaptation to satisfy TanStack's requirement; it only ever touches
    // apiClient's success path, never its thrown ApiError path, and does
    // not invent or read any response-body field.
    queryFn: async () => (await apiClient.get("/api/health/ready")) ?? null,
    // §16/§15: a liveness/readiness signal should never be considered
    // "fresh" from cache.
    staleTime: 0,
    // §15's own proposed value, disclosed in the T13a report: 2 retries
    // (initial attempt + 2 retries = 3 total attempts) — not the default
    // 3 retries, since a dev-only diagnostic shouldn't hang long before
    // telling the developer something's wrong.
    retry: 2,
    // §16's own proposed value: refetch every 15s while the tab has
    // focus.
    refetchInterval: 15_000,
    // §16: foreground-only — TanStack's own built-in option, not a manual
    // document.visibilitychange listener.
    refetchIntervalInBackground: false,
  } as const;
}

export function useReadiness(): UseReadinessResult {
  const query = useQuery<unknown, ApiError>(getReadinessQueryOptions());

  if (query.isLoading) {
    return { state: undefined, isLoading: true };
  }

  if (query.isSuccess) {
    // §16 "Healthy (2xx)" and "Malformed response body, 2xx case" rows:
    // apiClient already resolves a 2xx response successfully regardless
    // of whether its body parsed (see apiClient.ts) — the body's content
    // is never read here, since readiness is an HTTP-outcome signal, not
    // a response-body field (bekaa3d-api-contract: no invented payload
    // shape).
    return { state: "ready", isLoading: false };
  }

  // §16 "Unreachable"/"Timeout" rows map directly from apiClient's own
  // normalized ApiError.kind — never inspecting a raw TypeError or
  // building a second AbortController; that transport-level normalization
  // is entirely T09's job.
  if (query.isError && query.error.kind === "network") {
    return { state: "unreachable", isLoading: false };
  }
  if (query.isError && query.error.kind === "timeout") {
    return { state: "timeout", isLoading: false };
  }

  // §16 "Not ready" and "Malformed response body, non-2xx case" rows:
  // both ApiError.kind "http" (well-formed problem body) and "parse"
  // (malformed non-2xx body) land here. This is deliberate, not an
  // oversight — see the T13a report's status-preservation analysis:
  // apiClient only ever produces kind: "parse" from its non-2xx branch
  // (a 2xx response with a malformed body resolves successfully instead,
  // never reaching this code at all), so kind: "parse" is itself an
  // unambiguous "non-2xx response from a reachable server" signal, with
  // no need for the literal numeric status value §16 says isn't tied to
  // a specific code anyway ("handling is status-class-driven"). A
  // malformed body therefore never blocks ready/not-ready determination,
  // exactly as §16 requires.
  return { state: "not-ready", isLoading: false };
}
