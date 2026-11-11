import type { PriceRead, PublicImage } from "@/lib/catalog/productTypes";

// #FVS-OFFERS-TYPES (phase 6C)
//
// Transcribed from backend 2dfb27b openapi.json (components.schemas
// Offer*, AdminOffer*) and negotiation/api/offer_schemas.py. Offers exist
// only on STL products (negotiation/domain/offers.py `offer_refusal`), are
// USD-only (`currency: const "USD"`), and every amount is integer cents.

export type OfferStatus =
  | "awaiting_admin"
  | "awaiting_customer"
  | "accepted"
  | "rejected"
  | "expired"
  | "withdrawn"
  | "paid"
  | "checkout_expired"
  | "auto_closed";

export type OfferTurn = "admin" | "customer";

export type OfferAction =
  | "submitted"
  | "countered"
  | "accepted"
  | "rejected"
  | "withdrawn"
  | "expired"
  | "paid"
  | "checkout_expired"
  | "auto_closed";

export type OfferActor = "customer" | "admin" | "system";

// `allowed_actions` strings (OfferMove). The customer's set is counter,
// accept, withdraw; the administrator's is counter, accept, reject. Kept as
// a plain string on the wire so an unknown value is simply not rendered.
export type OfferMove = "counter" | "accept" | "reject" | "withdraw";

export interface OfferProductReadDTO {
  id: string;
  name: string | null;
  slug: string | null;
  cover_image: PublicImage | null;
}

export interface OfferRoundReadDTO {
  sequence: number;
  actor: OfferActor;
  action: OfferAction;
  amount: PriceRead | null;
  message: string | null;
  created_at: string;
}

export interface OfferSummaryReadDTO {
  id: string;
  product: OfferProductReadDTO;
  status: OfferStatus;
  turn: OfferTurn | null;
  current_amount: PriceRead;
  agreed_amount: PriceRead | null;
  responds_by: string | null;
  checkout_expires_at: string | null;
  created_at: string;
}

export interface OfferDetailReadDTO extends OfferSummaryReadDTO {
  initial_amount: PriceRead;
  cooldown_until: string | null;
  updated_at: string;
  rounds: OfferRoundReadDTO[];
  allowed_actions: string[];
}

export interface OfferCustomerReadDTO {
  id: string;
  email: string | null;
}

export interface AdminOfferSummaryReadDTO extends OfferSummaryReadDTO {
  customer: OfferCustomerReadDTO;
}

export interface AdminOfferDetailReadDTO extends OfferDetailReadDTO {
  customer: OfferCustomerReadDTO;
}

export interface OfferPageDTO {
  items: OfferSummaryReadDTO[];
  next_cursor: string | null;
}

export interface AdminOfferPageDTO {
  items: AdminOfferSummaryReadDTO[];
  next_cursor: string | null;
}

// Request bodies (all `additionalProperties: false`).
export interface OfferCreateDTO {
  product_id: string;
  amount_cents: number;
  currency: "USD";
  message?: string;
}

export interface OfferCounterRequestDTO {
  amount_cents: number;
  currency: "USD";
  message?: string;
}

export interface OfferAcceptRequestDTO {
  // `current_amount` exactly as the caller last saw it; anything else is
  // 409 OFFER_AMOUNT_CHANGED (ADR-035 d9).
  expected_amount_cents: number;
}

export interface OfferReasonRequestDTO {
  reason?: string;
}

// `payment_provider` is omitted, exactly as cart checkout omits it: the
// server chooses among its configured providers.
export interface OfferCheckoutRequestDTO {
  accept_terms: true;
  accept_digital_final_sale: true;
}

export const OFFER_CURRENCY = "USD" as const;
export const MAX_OFFER_MESSAGE = 1000;
