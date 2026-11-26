// FVS-003-IMPLEMENTATION-PLAN.md §9/Part E (confirmed BATCH 3B) —
// local-first logout (backend-recommended): local auth state is cleared
// synchronously, before any network response, then broadcast cross-tab,
// then the real server call is attempted. The frontend remains locally
// logged out regardless of the server outcome.
//
// Success semantics: 204 AND 401 AUTH_REQUIRED both count as confirmed
// server success; 403 CSRF_INVALID is explicitly NOT server success.
// Anything else not confirmed gets exactly one bounded background retry
// (never forever, no generic job framework, never routed through
// authenticatedRequest — logout must never trigger a refresh). The retry
// re-reads the CSRF cookie fresh via apiClient itself; if it's missing,
// apiClient's own local "csrf" error is simply the failure that ends the
// bounded retry — never fabricated.
//
// mutateAsync always resolves, never rejects: the user's own logout
// action is never a failed action, since the frontend is already locally
// logged out by the time any server outcome is known.
import { useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/apiClient";
import type { ApiError } from "@/lib/api/ApiError";
import { AUTH_SESSION_QUERY_KEY } from "./authSession";
import { createCrossTabSignal } from "./crossTabSignal";
import { clearUserScopedQueries } from "./userScopedQueries";

export interface LogoutResult {
  serverConfirmed: boolean;
}

const BACKGROUND_RETRY_DELAY_MS = 3_000;

function isAuthRequiredError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    (error as ApiError).kind === "http" &&
    (error as ApiError).status === 401 &&
    (error as ApiError).code === "AUTH_REQUIRED"
  );
}

async function attemptServerLogout(): Promise<boolean> {
  try {
    await apiClient.post("/api/v1/auth/logout", undefined, { csrf: true });
    return true;
  } catch (error) {
    return isAuthRequiredError(error);
  }
}

function scheduleOneBackgroundRetry(): void {
  setTimeout(() => {
    void attemptServerLogout();
  }, BACKGROUND_RETRY_DELAY_MS);
}

async function logout(queryClient: QueryClient): Promise<LogoutResult> {
  queryClient.setQueryData(AUTH_SESSION_QUERY_KEY, null);
  clearUserScopedQueries(queryClient);

  const signal = createCrossTabSignal();
  signal.announce("logout");
  signal.close();

  const serverConfirmed = await attemptServerLogout();
  if (!serverConfirmed) {
    scheduleOneBackgroundRetry();
  }

  return { serverConfirmed };
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => logout(queryClient),
    retry: false,
  });
}
