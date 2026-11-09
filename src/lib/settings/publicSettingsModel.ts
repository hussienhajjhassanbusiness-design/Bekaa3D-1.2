// #ARCHITECTURE-PUBLIC-SETTINGS-ADAPTER
//
// Current backend contract: docs/backend-handoff/openapi.json
// `PublicSettingsRead` (backend commit 2dfb27b). A fixed, flat object with
// exactly six REQUIRED keys:
//   accepting_orders: boolean
//   cash_payment_enabled: boolean
//   cash_max_order_total: MoneyRead (required, NOT nullable)
//   pickup_address / pickup_hours / whatsapp_number: string | null
//     (null = "not configured"; the UI hides the element)
// `free_shipping_threshold` was REMOVED by VS-028 (ADR-024: no shipping
// charge). It is absent from the wire type and the model.
//
// This shared model only mirrors the contract. No checkout behaviour reads
// the cash fields yet — the cash/checkout gating belongs to the checkout
// slice (FVS-026), and the backend stays authoritative for it there.
export interface MoneyModel {
  amountCents: number;
  currency: string;
}

export interface PublicSettingsModel {
  acceptingOrders: boolean;
  cashPaymentEnabled: boolean;
  cashMaxOrderTotal: MoneyModel;
  pickupAddress: string | null;
  pickupHours: string | null;
  whatsappNumber: string | null;
}

// Raw wire shape — openapi.json `PublicSettingsRead`, transcribed in full.
export interface PublicSettingsRead {
  accepting_orders: boolean;
  cash_payment_enabled: boolean;
  cash_max_order_total: { amount_cents: number; currency: string };
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
  return {
    acceptingOrders: raw.accepting_orders,
    cashPaymentEnabled: raw.cash_payment_enabled,
    cashMaxOrderTotal: {
      amountCents: raw.cash_max_order_total.amount_cents,
      currency: raw.cash_max_order_total.currency,
    },
    pickupAddress: raw.pickup_address,
    pickupHours: raw.pickup_hours,
    whatsappNumber: normalizeWhatsAppNumber(raw.whatsapp_number),
  };
}
