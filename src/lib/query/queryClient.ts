import { environmentManager, QueryClient } from "@tanstack/react-query";

// FRONTEND-VERTICAL-SLICE-PLAN.md §15 calls for a singleton QueryClient, but
// a literal module-level singleton (`export const queryClient = new
// QueryClient()`) is unsafe under Next.js App Router: any server-side use of
// a client created once at module scope would share its cache across every
// user's request — TanStack's own SSR guidance warns this "leaks any
// sensitive data." getQueryClient() resolves this safely: the server always
// gets a brand-new client per call (no cross-request state survives), while
// the browser genuinely reuses one instance via the module-scoped
// browserQueryClient variable below — a real singleton, but scoped to a
// single browser tab, never to the server process.
//
// No custom defaultOptions here — FVS-001 has no query yet with an opinion
// on staleTime/retry/gcTime. The first real query (FVS001-T13a) sets its own
// options at the query-hook level, not globally, so a health check's needs
// don't leak into every future domain (checkout, auth, catalogue...).
function makeQueryClient(): QueryClient {
  return new QueryClient();
}

let browserQueryClient: QueryClient | undefined;

export function getQueryClient(): QueryClient {
  if (environmentManager.isServer()) {
    return makeQueryClient();
  }
  if (!browserQueryClient) {
    browserQueryClient = makeQueryClient();
  }
  return browserQueryClient;
}
