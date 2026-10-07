// #ARCHITECTURE-WHATSAPP-ADAPTER
//
// Pure helpers only — kept out of the presentational component so phone
// normalization/message-building logic lives in exactly one place
// (never scattered across components). The public WhatsApp number
// setting's exact stored format is NOT confirmed
// (FVS-014-IMPLEMENTATION-PLAN.md §1) — `vertical-slice-plan.md` only
// names "WhatsApp number" as a seeded setting, with no format given.
//
// This module does NOT normalize an arbitrary setting value — that
// would mean inventing a normalization rule (strip a "+", strip
// spaces/hyphens, assume a country code) with no evidence it's correct.
// Its precondition is explicit and enforced, not assumed: the caller
// (a future settings adapter, once the real format is confirmed) must
// supply `normalizedNumber` as digits only. A value that doesn't meet
// that precondition is rejected outright (`null`), never "cleaned up."
export function buildWhatsAppHref(normalizedNumber: string, message: string): string | null {
  if (!/^\d+$/.test(normalizedNumber)) {
    return null;
  }
  return `https://wa.me/${normalizedNumber}?text=${encodeURIComponent(message)}`;
}

// Frontend-owned default copy — VS-013/VS-007 confirm only that the
// product name must appear in the prefilled message (FVS-014's own
// Testing line); the exact wording is not a backend contract item and
// may be revised once real product/brand copy guidelines exist.
export function buildWhatsAppProductMessage(productName: string): string {
  return `Hi, I'm interested in "${productName}".`;
}
