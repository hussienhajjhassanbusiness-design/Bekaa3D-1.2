"use client";

import { useMemo } from "react";
import { OrderHistoryList } from "@/components/account/OrderHistoryList";
import { PageHeader } from "@/components/ui/PageHeader";
import { adaptOrderSummary } from "@/lib/orders/orderModel";
import { useMyOrders } from "@/lib/orders/useMyOrders";

// FVS-029 (phase 5E) — the customer's order history, GET /api/v1/me/orders.
// AccountLayout (src/app/account/layout.tsx) supplies ProtectedRoute, the
// account nav and the content landmark; this page renders only content.
export default function AccountOrdersPage() {
  const query = useMyOrders();
  const orders = useMemo(
    () => (query.data?.pages ?? []).flatMap((page) => page.items).map(adaptOrderSummary),
    [query.data]
  );
  const hasData = query.data !== undefined;

  return (
    <>
      <PageHeader
        eyebrow="Account"
        title="Orders"
        description="Every order you've placed, newest first. Open one to see its items, payment and updates."
      />
      <div>
        <OrderHistoryList
          orders={orders}
          isLoading={query.isLoading}
          // Before any page loads, a failure replaces the list; after, a
          // failed "Load more" keeps the loaded orders on screen.
          error={hasData ? null : query.error}
          onRetry={() => void query.refetch()}
          hasNextPage={query.hasNextPage}
          isFetchingNextPage={query.isFetchingNextPage}
          onLoadMore={() => void query.fetchNextPage()}
          loadMoreFailed={hasData && query.isFetchNextPageError}
        />
      </div>
    </>
  );
}
