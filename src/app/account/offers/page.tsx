"use client";

import { useMemo } from "react";
import { OfferList } from "@/components/offers/OfferList";
import { PageHeader } from "@/components/ui/PageHeader";
import { useMyOffers } from "@/lib/offers/useOffers";

// FVS (phase 6C) — the customer's offers, GET /api/v1/me/offers (newest
// first). AccountLayout supplies ProtectedRoute, the account nav and the
// content landmark; this page renders only content.
export default function AccountOffersPage() {
  const query = useMyOffers();
  const offers = useMemo(() => (query.data?.pages ?? []).flatMap((page) => page.items), [query.data]);
  const hasData = query.data !== undefined;

  return (
    <>
      <PageHeader
        eyebrow="Account"
        title="Offers"
        description="Your price offers on STL files. When it's your turn, reply before the deadline or the offer expires."
      />
      <div>
        <OfferList
          offers={offers}
          isLoading={query.isLoading}
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
