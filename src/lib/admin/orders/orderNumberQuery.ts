// `GET /api/v1/admin/orders?order_number=` (openapi: string, 1..40 chars)
// is an EXACT, case-sensitive match on the backend-owned public order
// number (backend `admin_orders.py`: `column == value`; docs/fulfillment.md
// "exact match"). Order numbers are always upper case (`B3D-` + 8 Crockford
// base32 characters, ADR-032), so trimming and upper-casing what the admin
// typed can only turn a near-miss ("b3d-7njv7hx7 ") into the real number —
// it never widens the match. No partial or prefix search exists, so the UI
// must not promise one.
export const ORDER_NUMBER_QUERY_MAX_LENGTH = 40;

export function normalizeOrderNumberQuery(raw: string): string | undefined {
  const value = raw.trim().toUpperCase();
  return value === "" ? undefined : value.slice(0, ORDER_NUMBER_QUERY_MAX_LENGTH);
}
