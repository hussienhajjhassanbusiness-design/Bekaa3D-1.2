import { useInfiniteQuery } from "@tanstack/react-query";
import { productsApi, productsKeys } from "./productsApi";
import type { ProductsQueryParams } from "./productTypes";

// #ARCHITECTURE-PRODUCTS-LIST-QUERY
//
// `useInfiniteQuery` matches the backend's own pagination shape exactly
// (C2: `{items, next_cursor}`, no total/page number/has_more) — "load
// more" appends a page rather than replacing it, and `hasNextPage` is
// derived straight from `next_cursor !== null`, never a guessed page
// count. Changing any filter/sort/search param changes the query key,
// which starts a fresh first page automatically (TanStack's own behavior)
// — matching shopUrlState's own "clear the cursor when a filter changes"
// rule on the URL side.
//
// `params.cursor`, if present, seeds `initialPageParam` — this is how a
// shared/reloaded `/shop?...&cursor=X` URL resumes forward from that exact
// point rather than always restarting at page one. It is a genuine
// resumption (a real `GET /products?cursor=X`), not a reconstruction of
// every previously-loaded page: reloading a URL with a cursor shows the
// one page starting there, not the full accumulated scroll history, which
// a single opaque cursor cannot reconstruct anyway (C2: cursors are not
// random-access).
export function useProducts(params: ProductsQueryParams) {
  return useInfiniteQuery({
    queryKey: productsKeys.list(params),
    queryFn: ({ pageParam }) => productsApi.listProducts({ ...params, cursor: pageParam ?? undefined }),
    initialPageParam: params.cursor,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}
