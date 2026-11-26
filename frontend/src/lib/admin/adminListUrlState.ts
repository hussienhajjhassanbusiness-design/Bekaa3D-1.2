export interface AdminListUrlState {
  q: string;
  page: number;
}

// #ARCHITECTURE-ADMIN-LIST-URL-STATE
//
// Pure browser-URL-state helpers ONLY. This is NOT the backend query
// adapter — the backend's own search/page query-parameter names are
// still NEEDS BACKEND CONFIRMATION
// (FVS-009-IMPLEMENTATION-PLAN.md §1). These functions only read/write
// the browser's own `q`/`page` convention
// (FRONTEND-VERTICAL-SLICE-PLAN.md's own State line), never call fetch,
// and never touch `window`/history — callers wire that in the real route
// (T06, still blocked).
//
// Deliberately does not reset page to 1 as a side effect of changing q:
// nothing in the governing plans confirms that as required behavior at
// this layer (plan §5) — a caller that wants it passes `page: 1`
// explicitly alongside its own q update.
export function parseAdminListUrlState(params: URLSearchParams): AdminListUrlState {
  const q = params.get("q") ?? "";

  const rawPage = params.get("page");
  const parsedPage = rawPage === null ? NaN : Number(rawPage);
  const page = Number.isInteger(parsedPage) && parsedPage > 0 ? parsedPage : 1;

  return { q, page };
}

export function buildAdminListUrlParams(
  current: URLSearchParams,
  updates: Partial<AdminListUrlState>
): URLSearchParams {
  const next = new URLSearchParams(current);

  if (updates.q !== undefined) {
    if (updates.q === "") {
      next.delete("q");
    } else {
      next.set("q", updates.q);
    }
  }

  if (updates.page !== undefined) {
    if (updates.page <= 1) {
      next.delete("page");
    } else {
      next.set("page", String(updates.page));
    }
  }

  return next;
}
