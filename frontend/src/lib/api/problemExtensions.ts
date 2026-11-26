import type { ApiError } from "./ApiError";

// RFC 9457 extension members (e.g. `max_quantity` on
// QUANTITY_EXCEEDS_LIMIT, `reason` on PRODUCT_NOT_PURCHASABLE) are
// top-level members of the Problem body. parseProblemBody keeps the whole
// body in `raw`; these readers pull one member out with a strict type
// check. A wrong-typed member is treated as absent, never coerced. Callers
// read only members that a documented Problem code defines.

function member(error: ApiError, key: string): unknown {
  const raw = error.raw;
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    return undefined;
  }
  return (raw as Record<string, unknown>)[key];
}

export function readProblemInteger(error: ApiError, key: string): number | undefined {
  const value = member(error, key);
  return typeof value === "number" && Number.isInteger(value) ? value : undefined;
}

export function readProblemString(error: ApiError, key: string): string | undefined {
  const value = member(error, key);
  return typeof value === "string" ? value : undefined;
}

// An array member (e.g. `price_changes`, `lines`, `product_ids`,
// `dropped_lines`). The elements are returned unvalidated: the caller
// checks each one against its documented shape and drops what does not fit.
export function readProblemArray(error: ApiError, key: string): readonly unknown[] | undefined {
  const value = member(error, key);
  return Array.isArray(value) ? value : undefined;
}
