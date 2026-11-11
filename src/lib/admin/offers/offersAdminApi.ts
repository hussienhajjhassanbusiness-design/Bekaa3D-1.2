import { apiClient } from "@/lib/api/apiClient";
import { adminRequest } from "@/lib/admin/adminRequest";
import {
  OFFER_CURRENCY,
  type AdminOfferDetailReadDTO,
  type AdminOfferPageDTO,
  type OfferAcceptRequestDTO,
  type OfferCounterRequestDTO,
  type OfferReasonRequestDTO,
  type OfferStatus,
} from "@/lib/offers/offerTypes";

// #FVS-OFFERS-ADMIN-API (phase 6C) — backend 2dfb27b
// negotiation/api/admin_offers.py. Admin boundary: a non-admin gets 404,
// no session / MFA incomplete is 401 (adminRequest routes MFA_REQUIRED to
// the shared MFA signal).
//   GET  /api/v1/admin/offers?status&product_id&user_id&responds_before&cursor&limit
//        -> {items, next_cursor}. Queue order: the administrator's turn
//        first, then the soonest deadline.
//   GET  /api/v1/admin/offers/{id}            -> AdminOfferDetailRead
//   POST /{id}/accept   {expected_amount_cents}    CSRF; agreed = min(current, list price)
//   POST /{id}/counter  {amount_cents, currency, message?} CSRF; <= list price
//   POST /{id}/reject   {reason?} or no body       CSRF; arms the customer's cooldown

export interface AdminOffersQueryParams {
  status?: OfferStatus;
  cursor?: string;
  limit?: number;
}

const BASE = "/api/v1/admin/offers";

function path(offerId: string, action?: string): string {
  const base = `${BASE}/${encodeURIComponent(offerId)}`;
  return action ? `${base}/${action}` : base;
}

function optionalText(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

function listOffers(params: AdminOffersQueryParams): Promise<AdminOfferPageDTO> {
  const search = new URLSearchParams();
  if (params.status) search.set("status", params.status);
  if (params.cursor) search.set("cursor", params.cursor);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  const q = search.toString();
  return adminRequest(() => apiClient.get<AdminOfferPageDTO>(q ? `${BASE}?${q}` : BASE));
}

function getOffer(offerId: string): Promise<AdminOfferDetailReadDTO> {
  return adminRequest(() => apiClient.get<AdminOfferDetailReadDTO>(path(offerId)));
}

function acceptOffer(offerId: string, expectedAmountCents: number): Promise<AdminOfferDetailReadDTO> {
  const body: OfferAcceptRequestDTO = { expected_amount_cents: expectedAmountCents };
  return adminRequest(() => apiClient.post<AdminOfferDetailReadDTO>(path(offerId, "accept"), body, { csrf: true }));
}

function counterOffer(offerId: string, amountCents: number, message?: string): Promise<AdminOfferDetailReadDTO> {
  const note = optionalText(message);
  const body: OfferCounterRequestDTO = { amount_cents: amountCents, currency: OFFER_CURRENCY, ...(note ? { message: note } : {}) };
  return adminRequest(() => apiClient.post<AdminOfferDetailReadDTO>(path(offerId, "counter"), body, { csrf: true }));
}

function rejectOffer(offerId: string, reason?: string): Promise<AdminOfferDetailReadDTO> {
  const note = optionalText(reason);
  const body: OfferReasonRequestDTO | undefined = note ? { reason: note } : undefined;
  return adminRequest(() => apiClient.post<AdminOfferDetailReadDTO>(path(offerId, "reject"), body, { csrf: true }));
}

export const offersAdminApi = { listOffers, getOffer, acceptOffer, counterOffer, rejectOffer };

// Under the user-scoped ["admin"] root (cleared on sign-out / user switch).
export const adminOfferKeys = {
  root: ["admin", "offers"] as const,
  lists: () => [...adminOfferKeys.root, "list"] as const,
  list: (params: AdminOffersQueryParams) => [...adminOfferKeys.lists(), params] as const,
  detail: (offerId: string) => [...adminOfferKeys.root, "detail", offerId] as const,
};
