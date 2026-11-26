import type { AdminOfferDetailReadDTO, OfferDetailReadDTO } from "./offerTypes";

// Test fixtures shaped exactly like backend 2dfb27b OfferDetailRead /
// AdminOfferDetailRead.
export const OFFER_ID = "00000000-0000-4000-8000-0000000000a1";
export const OFFER_PRODUCT_ID = "00000000-0000-4000-8000-0000000000b1";

export function offerDetail(overrides: Partial<OfferDetailReadDTO> = {}): OfferDetailReadDTO {
  return {
    id: OFFER_ID,
    product: { id: OFFER_PRODUCT_ID, name: "Dragon STL", slug: "dragon-stl", cover_image: null },
    status: "awaiting_admin",
    turn: "admin",
    current_amount: { amount_cents: 1500, currency: "USD" },
    agreed_amount: null,
    responds_by: "2026-11-14T10:00:00Z",
    checkout_expires_at: null,
    created_at: "2026-11-12T10:00:00Z",
    initial_amount: { amount_cents: 1500, currency: "USD" },
    cooldown_until: null,
    updated_at: "2026-11-12T10:00:00Z",
    rounds: [
      {
        sequence: 1,
        actor: "customer",
        action: "submitted",
        amount: { amount_cents: 1500, currency: "USD" },
        message: "<b>Would you take $15?</b>",
        created_at: "2026-11-12T10:00:00Z",
      },
    ],
    allowed_actions: ["withdraw"],
    ...overrides,
  };
}

export function adminOfferDetail(overrides: Partial<AdminOfferDetailReadDTO> = {}): AdminOfferDetailReadDTO {
  return {
    ...offerDetail({ allowed_actions: ["counter", "accept", "reject"] }),
    customer: { id: "00000000-0000-4000-8000-0000000000c1", email: "rana@example.com" },
    ...overrides,
  };
}
