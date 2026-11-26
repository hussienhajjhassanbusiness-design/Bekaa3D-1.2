// #ARCHITECTURE-CANONICAL-OFFERS-QUERY (phase 6C)
//
// The ONE query-key family for the customer's own offers
// (GET /api/v1/me/offers, GET /api/v1/me/offers/{id}). The product page's
// "you already have an offer" check, the account list and the detail page
// all read these keys, and every write stores the server's OfferDetailRead
// back into `detail(id)`.
//
// User scoping: `root` is dropped on logout, on a cross-tab logout and
// before every new sign-in (userScopedQueries.ts). The administrator's
// queue lives under the separate ["admin", "offers"] root.
export interface OfferListParams {
  limit?: number;
  productId?: string;
}

export const offerKeys = {
  root: ["offers"] as const,
  lists: () => [...offerKeys.root, "list"] as const,
  list: (params: OfferListParams) => [...offerKeys.lists(), params] as const,
  detail: (offerId: string) => [...offerKeys.root, "detail", offerId] as const,
};
