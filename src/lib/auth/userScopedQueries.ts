import type { QueryClient } from "@tanstack/react-query";

// Phase 5A defect 7 — cache roots that hold one signed-in user's data
// (admin screens, the account notification list). Dropped on logout so a
// later sign-in in the same tab can never see the previous user's cached
// rows, even briefly while refetching. Phase 5B adds the address book
// (`addressKeys.root`): saved addresses are personal data. Phase 5C adds
// the cart (`cartKeys.root`). Phase 5E adds the customer's orders
// (`orderKeys.root`): order history, addresses and phone are personal
// data. Public catalogue/settings caches
// are user-independent and stay. Any future user-scoped key root must be
// added here.
const USER_SCOPED_QUERY_ROOTS: readonly (readonly string[])[] = [
  ["admin"],
  ["notifications"],
  ["addresses"],
  ["cart"],
  ["orders"],
  // Phase 6C: the customer's own offers (amounts and messages are personal).
  ["offers"],
];

export function clearUserScopedQueries(queryClient: QueryClient): void {
  for (const queryKey of USER_SCOPED_QUERY_ROOTS) {
    queryClient.removeQueries({ queryKey });
  }
}
