export interface ShopUrlState {
  category: string | null;
  material: string | null;
  colour: string | null;
  sort: string | null;
  q: string;
  cursor: string | null;
}

const FACET_KEYS = ["category", "material", "colour"] as const;

// #ARCHITECTURE-CATALOGUE-URL-STATE
//
// Pure browser-URL-state helpers for /shop ONLY — not the backend query
// adapter. The literal keys (`category`/`material`/`colour`/`sort`/`q`/
// `cursor`) are confirmed by FRONTEND-VERTICAL-SLICE-PLAN.md's own
// routing line; the backend's own query-parameter names/shapes are a
// separate, still-unconfirmed concern (FVS-013-IMPLEMENTATION-PLAN.md
// §1). Only single-value facets are supported — the route examples show
// singular keys, and no governing evidence defines a multi-value
// serialization strategy, so one is not invented here.
//
// `cursor` is always treated as an opaque string — this module never
// parses, decodes, or constructs one.
export function parseShopUrlState(params: URLSearchParams): ShopUrlState {
  function readFacet(key: string): string | null {
    const value = params.get(key);
    return value === null || value === "" ? null : value;
  }

  return {
    category: readFacet("category"),
    material: readFacet("material"),
    colour: readFacet("colour"),
    sort: readFacet("sort"),
    q: params.get("q") ?? "",
    cursor: readFacet("cursor"),
  };
}

// Changing any filter/sort/search dimension clears the cursor: a cursor
// token is only valid for the exact query that produced it, so carrying
// it into a different query would silently request pagination against a
// result set that no longer matches what's on screen. This is a frontend
// URL-hygiene invariant, not a claim about the backend's cursor format.
export function buildShopUrlParams(current: URLSearchParams, updates: Partial<ShopUrlState>): URLSearchParams {
  const next = new URLSearchParams(current);
  let shouldClearCursor = false;

  for (const key of [...FACET_KEYS, "sort", "q"] as const) {
    if (!(key in updates)) {
      continue;
    }
    const value: string | null | undefined = updates[key];
    if (!value) {
      next.delete(key);
    } else {
      next.set(key, value);
    }
    shouldClearCursor = true;
  }

  if ("cursor" in updates) {
    const value = updates.cursor;
    if (value === null || value === undefined) {
      next.delete("cursor");
    } else {
      next.set("cursor", value);
    }
  } else if (shouldClearCursor) {
    next.delete("cursor");
  }

  return next;
}
