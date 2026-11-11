import { apiClient } from "@/lib/api/apiClient";
import { authenticatedRequest } from "@/lib/auth/authenticatedRequest";
import { CHECKOUT_TIMEOUT_MS } from "@/lib/checkout/checkoutApi";
import type { CheckoutReadDTO } from "@/lib/checkout/checkoutTypes";
import {
  OFFER_CURRENCY,
  type OfferAcceptRequestDTO,
  type OfferCheckoutRequestDTO,
  type OfferCounterRequestDTO,
  type OfferCreateDTO,
  type OfferDetailReadDTO,
  type OfferPageDTO,
  type OfferReasonRequestDTO,
} from "./offerTypes";

// #ARCHITECTURE-CUSTOMER-OFFERS-API (phase 6C)
//
// Backend 2dfb27b negotiation/api/offers.py and ordering/api/offer_checkout.py:
//   POST /api/v1/offers                       open an offer (STL only)
//   GET  /api/v1/me/offers?status&product_id&cursor&limit
//   GET  /api/v1/me/offers/{id}               with the full round history
//   POST /api/v1/me/offers/{id}/counter       {amount_cents, currency, message?}
//   POST /api/v1/me/offers/{id}/accept        {expected_amount_cents}
//   POST /api/v1/me/offers/{id}/withdraw      {reason?} or no body
//   POST /api/v1/me/offers/{id}/checkout      Idempotency-Key, consents
// Reads need only a session. Every write needs a verified email, the
// double-submit X-CSRF-Token and spends a per-user hourly budget (20 opens,
// 60 answers; checkout shares cart checkout's). Answers return the full
// OfferDetailRead. None of the answers is idempotency-keyed: the shared
// refresh-on-401-then-retry-once wrapper resends the identical request only
// after a 401, which the server answers before the route body runs.

export interface ListMyOffersParams {
  productId?: string;
  cursor?: string;
  limit?: number;
}

function offerPath(offerId: string, action?: string): string {
  const base = `/api/v1/me/offers/${encodeURIComponent(offerId)}`;
  return action ? `${base}/${action}` : base;
}

function optionalText(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

function listMyOffers(params: ListMyOffersParams = {}): Promise<OfferPageDTO> {
  const search = new URLSearchParams();
  if (params.productId) search.set("product_id", params.productId);
  if (params.cursor) search.set("cursor", params.cursor);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  const q = search.toString();
  return authenticatedRequest(() => apiClient.get<OfferPageDTO>(q ? `/api/v1/me/offers?${q}` : "/api/v1/me/offers"));
}

function getMyOffer(offerId: string): Promise<OfferDetailReadDTO> {
  return authenticatedRequest(() => apiClient.get<OfferDetailReadDTO>(offerPath(offerId)));
}

function createOffer(input: { productId: string; amountCents: number; message?: string }): Promise<OfferDetailReadDTO> {
  const message = optionalText(input.message);
  const body: OfferCreateDTO = {
    product_id: input.productId,
    amount_cents: input.amountCents,
    currency: OFFER_CURRENCY,
    ...(message ? { message } : {}),
  };
  return authenticatedRequest(() => apiClient.post<OfferDetailReadDTO>("/api/v1/offers", body, { csrf: true }));
}

function counterOffer(offerId: string, amountCents: number, message?: string): Promise<OfferDetailReadDTO> {
  const note = optionalText(message);
  const body: OfferCounterRequestDTO = { amount_cents: amountCents, currency: OFFER_CURRENCY, ...(note ? { message: note } : {}) };
  return authenticatedRequest(() => apiClient.post<OfferDetailReadDTO>(offerPath(offerId, "counter"), body, { csrf: true }));
}

function acceptOffer(offerId: string, expectedAmountCents: number): Promise<OfferDetailReadDTO> {
  const body: OfferAcceptRequestDTO = { expected_amount_cents: expectedAmountCents };
  return authenticatedRequest(() => apiClient.post<OfferDetailReadDTO>(offerPath(offerId, "accept"), body, { csrf: true }));
}

function withdrawOffer(offerId: string, reason?: string): Promise<OfferDetailReadDTO> {
  const note = optionalText(reason);
  const body: OfferReasonRequestDTO | undefined = note ? { reason: note } : undefined;
  return authenticatedRequest(() => apiClient.post<OfferDetailReadDTO>(offerPath(offerId, "withdraw"), body, { csrf: true }));
}

// The key and the fixed body are captured once in this closure, so the
// refresh-and-retry wrapper can only resend the identical request, which the
// server replays instead of placing a second order.
function checkoutOffer(offerId: string, idempotencyKey: string): Promise<CheckoutReadDTO> {
  const body: OfferCheckoutRequestDTO = { accept_terms: true, accept_digital_final_sale: true };
  return authenticatedRequest(() =>
    apiClient.post<CheckoutReadDTO>(offerPath(offerId, "checkout"), body, {
      csrf: true,
      headers: { "Idempotency-Key": idempotencyKey },
      timeoutMs: CHECKOUT_TIMEOUT_MS,
    })
  );
}

export const offersApi = { listMyOffers, getMyOffer, createOffer, counterOffer, acceptOffer, withdrawOffer, checkoutOffer };
