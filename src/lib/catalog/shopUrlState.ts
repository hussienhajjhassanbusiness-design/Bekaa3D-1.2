export interface ShopUrlState {
  category: readonly string[];
  material: readonly string[];
  colour: readonly string[];
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
// §1).
//
// Facet cardinality is explicitly NOT assumed: the source requires
// checkbox-based facets, and the backend has not confirmed whether a
// facet permits one or many selected values, nor how multiple values
// would serialize. So the MODEL is cardinality-neutral — each facet is
// `readonly string[]` (zero, one, or many) — while the actual URL
// encoding for more than one value per facet stays an explicit, loud
// gate (`#BACKEND-GATE-FACET-SERIALIZATION` in buildShopUrlParams)
// rather than a guessed repeated-param/comma/pipe/JSON scheme. Reading
// uses `URLSearchParams.getAll`, which is the web platform's own neutral
// way to read however many same-named params are already present — this
// is not this module choosing an encoding, only not losing data if one
// already exists in the URL.
//
// `cursor` is always treated as an opaque string — this module never
// parses, decodes, or constructs one.
export function parseShopUrlState(params: URLSearchParams): ShopUrlState {
  function readFacetValues(key: string): readonly string[] {
    return params.getAll(key).filter((value) => value !== "");
  }

  function readSingle(key: string): string | null {
    const value = params.get(key);
    return value === null || value === "" ? null : value;
  }

  return {
    category: readFacetValues("category"),
    material: readFacetValues("material"),
    colour: readFacetValues("colour"),
    sort: readSingle("sort"),
    q: params.get("q") ?? "",
    cursor: readSingle("cursor"),
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

  for (const key of FACET_KEYS) {
    if (!(key in updates)) {
      continue;
    }
    const values = updates[key];
    next.delete(key);
    if (values && values.length > 0) {
      // #BACKEND-GATE-FACET-SERIALIZATION
      //
      // Writing exactly one value reuses the only encoding the source
      // actually confirms (a single `key=value` pair, per the literal
      // route example). Writing more than one value would require
      // choosing an encoding (repeated params? comma-separated? pipe?
      // JSON?) that the backend has not confirmed — rather than guess,
      // this throws loudly so the gap can never be silently shipped.
      // A future caller/adapter resolves this once VS-013/VS-010 confirm
      // the real multi-value contract.
      if (values.length > 1) {
        throw new Error(
          `buildShopUrlParams: multi-value "${key}" facet serialization is NEEDS BACKEND CONFIRMATION — ` +
            `refusing to guess an encoding for ${values.length} values.`
        );
      }
      next.set(key, values[0]!);
    }
    shouldClearCursor = true;
  }

  for (const key of ["sort", "q"] as const) {
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
