import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ApiError } from "@/lib/api/ApiError";
import { orderKeys } from "@/lib/orders/orderKeys";
import { offerKeys } from "./offerKeys";
import { offersApi } from "./offersApi";
import type { OfferDetailReadDTO, OfferPageDTO } from "./offerTypes";

// #ARCHITECTURE-CUSTOMER-OFFERS-QUERIES (phase 6C)
//
// List: useInfiniteQuery on the backend's {items, next_cursor} page, newest
// first. Detail: one query per id; a 404/422 (unknown, someone else's or a
// malformed id: the same answer) and a 401 are final, a transport/5xx
// failure is retried once. Every write stores the server's OfferDetailRead
// into the canonical detail key and invalidates the lists; nothing is set
// optimistically. Writes are never retried automatically.
export const OFFER_LIST_PAGE_SIZE = 20;

function retryOnce(failureCount: number, error: unknown): boolean {
  const e = error as ApiError | undefined;
  const final = e?.kind === "http" && (e.status === 401 || e.status === 404 || e.status === 422);
  return !final && failureCount < 1;
}

export function useMyOffers() {
  const params = { limit: OFFER_LIST_PAGE_SIZE };
  return useInfiniteQuery<OfferPageDTO, ApiError, { pages: OfferPageDTO[] }, ReturnType<typeof offerKeys.list>, string | undefined>({
    queryKey: offerKeys.list(params),
    queryFn: ({ pageParam }) => offersApi.listMyOffers({ ...params, cursor: pageParam }),
    initialPageParam: undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    retry: retryOnce,
  });
}

// The product page's check for an offer already in progress on this
// product (one small page, filtered server-side by product_id).
export function useMyOffersForProduct(productId: string, enabled: boolean) {
  const params = { productId, limit: 5 };
  return useQuery<OfferPageDTO, ApiError>({
    queryKey: offerKeys.list(params),
    queryFn: () => offersApi.listMyOffers(params),
    enabled,
    retry: retryOnce,
  });
}

export function useMyOffer(offerId: string, enabled = true) {
  return useQuery<OfferDetailReadDTO, ApiError>({
    queryKey: offerKeys.detail(offerId),
    queryFn: () => offersApi.getMyOffer(offerId),
    enabled,
    retry: retryOnce,
  });
}

function useStoreOffer() {
  const queryClient = useQueryClient();
  return (offer: OfferDetailReadDTO) => {
    queryClient.setQueryData(offerKeys.detail(offer.id), offer);
    return queryClient.invalidateQueries({ queryKey: offerKeys.lists() });
  };
}

export function useCreateOffer() {
  const store = useStoreOffer();
  return useMutation({
    mutationFn: (input: Parameters<typeof offersApi.createOffer>[0]) => offersApi.createOffer(input),
    retry: false,
    onSuccess: (offer) => store(offer),
  });
}

export type CustomerOfferAnswer =
  | { move: "counter"; amountCents: number; message?: string }
  | { move: "accept"; expectedAmountCents: number }
  | { move: "withdraw"; reason?: string };

export function useAnswerOffer(offerId: string) {
  const store = useStoreOffer();
  return useMutation({
    mutationFn: (answer: CustomerOfferAnswer) => {
      switch (answer.move) {
        case "counter":
          return offersApi.counterOffer(offerId, answer.amountCents, answer.message);
        case "accept":
          return offersApi.acceptOffer(offerId, answer.expectedAmountCents);
        case "withdraw":
          return offersApi.withdrawOffer(offerId, answer.reason);
      }
    },
    retry: false,
    onSuccess: (offer) => store(offer),
  });
}

// A placed order changes the customer's order history; the offer itself
// stays `accepted` until the payment is verified, so it is re-read too.
export function useOfferCheckout(offerId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (idempotencyKey: string) => offersApi.checkoutOffer(offerId, idempotencyKey),
    retry: false,
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: offerKeys.root }),
        queryClient.invalidateQueries({ queryKey: orderKeys.root }),
      ]),
  });
}
