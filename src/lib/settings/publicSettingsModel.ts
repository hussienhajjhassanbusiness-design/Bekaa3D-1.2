// #ARCHITECTURE-PUBLIC-SETTINGS-ADAPTER
//
// A frontend-normalized shape — UPDATE (REAL STOREFRONT INTEGRATION PHASE
// 1): the response shape is now CONFIRMED, not provisional. BACKEND-
// RESPONSE.md B1 / openapi.json `PublicSettingsRead` is a fixed, flat
// object with exactly five keys (`accepting_orders`, `whatsapp_number`,
// `pickup_address`, `pickup_hours`, `free_shipping_threshold`) — not a
// `{key, value}[]` list as an earlier draft of this comment speculated.
// This module still holds ONLY the one field this phase's components
// actually consume (WhatsApp), and deliberately does NOT add a
// free-shipping-threshold field: B1 states that field is already obsolete
// (`null` today, slated for removal once VS-028 lands) — building UI
// around it would be building on a field the backend itself says to
// ignore.
export interface PublicSettingsModel {
  whatsappNumber: string | null;
}

// Raw wire shape — openapi.json `PublicSettingsRead`, transcribed in
// full even though this module's model only surfaces one field today, so
// a future consumer (pickup info, accepting_orders) extends this same
// raw/adapter pair instead of re-deriving the wire contract.
export interface PublicSettingsRead {
  accepting_orders: boolean;
  free_shipping_threshold: { amount_cents: number; currency: string } | null;
  pickup_address: string | null;
  pickup_hours: string | null;
  whatsapp_number: string | null;
}

// `whatsapp_number` is confirmed E.164 (B1's own example: "+96170000000").
// `buildWhatsAppHref` (lib/catalog/whatsapp.ts) requires digits-only by
// design — this is the one place that strips everything but digits,
// matching the E.164-to-digits-only convention that module's own comment
// anticipated ("once the real format is confirmed"). A non-digit-leading
// value therefore still normalizes correctly; an already-empty/garbage
// value normalizes to an empty string, which buildWhatsAppHref's own
// `/^\d+$/` precondition then safely rejects (returns null) rather than
// this adapter guessing a fallback.
function normalizeWhatsAppNumber(raw: string | null): string | null {
  if (!raw) {
    return null;
  }
  const digitsOnly = raw.replace(/\D/g, "");
  return digitsOnly.length > 0 ? digitsOnly : null;
}

export function toPublicSettingsModel(raw: PublicSettingsRead): PublicSettingsModel {
  return { whatsappNumber: normalizeWhatsAppNumber(raw.whatsapp_number) };
}
