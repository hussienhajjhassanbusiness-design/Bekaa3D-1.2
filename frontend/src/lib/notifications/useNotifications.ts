import { useInfiniteQuery } from "@tanstack/react-query";
import { notificationsApi, notificationsKeys } from "./notificationsApi";
import type { NotificationsQueryParams } from "./notificationTypes";

// #ARCHITECTURE-NOTIFICATIONS-LIST-QUERY — mirrors useProducts.ts exactly:
// useInfiniteQuery matching the backend's own {items, next_cursor} shape
// (no total/page-number/has_more field exists). "Load more" appends a
// page; hasNextPage is derived straight from next_cursor !== null.
export function useNotifications(params: Omit<NotificationsQueryParams, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: notificationsKeys.list(params),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      notificationsApi.listNotifications({ ...params, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}
