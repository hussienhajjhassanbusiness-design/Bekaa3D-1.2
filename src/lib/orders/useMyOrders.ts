import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { classifyOrderError } from "./orderErrors";
import { orderKeys } from "./orderKeys";
import { ordersApi } from "./ordersApi";

// #ARCHITECTURE-CUSTOMER-ORDERS-QUERIES
//
// History: useInfiniteQuery on the backend's own {items, next_cursor}
// page (no total/page-number exists). "Load more" appends the next page;
// hasNextPage is exactly `next_cursor !== null`.
//
// Detail: one query per order id. A not-found/auth failure is final, so
// it is never retried (a retry cannot change a 404); a transport/5xx
// failure is retried once.
export const ORDER_HISTORY_PAGE_SIZE = 20;

function retryOnce(failureCount: number, error: unknown): boolean {
  return classifyOrderError(error) === "generic" && failureCount < 1;
}

export function useMyOrders() {
  const params = { limit: ORDER_HISTORY_PAGE_SIZE };
  return useInfiniteQuery({
    queryKey: orderKeys.list(params),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      ordersApi.listMyOrders({ ...params, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    retry: retryOnce,
  });
}

export function useMyOrder(orderId: string, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: orderKeys.detail(orderId),
    queryFn: () => ordersApi.getMyOrder(orderId),
    enabled: options.enabled ?? true,
    retry: retryOnce,
  });
}
