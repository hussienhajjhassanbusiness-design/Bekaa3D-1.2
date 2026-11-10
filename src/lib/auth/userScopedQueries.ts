import type { QueryClient } from "@tanstack/react-query";

// Phase 5A defect 7 — cache roots that hold one signed-in user's data
// (admin screens, the account notification list). Dropped on logout so a
// later sign-in in the same tab can never see the previous user's cached
// rows, even briefly while refetching. Public catalogue/settings caches
// are user-independent and stay. Any future user-scoped key root must be
// added here.
const USER_SCOPED_QUERY_ROOTS: readonly (readonly string[])[] = [["admin"], ["notifications"]];

export function clearUserScopedQueries(queryClient: QueryClient): void {
  for (const queryKey of USER_SCOPED_QUERY_ROOTS) {
    queryClient.removeQueries({ queryKey });
  }
}
