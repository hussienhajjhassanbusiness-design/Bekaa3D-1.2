import Link from "next/link";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { Button } from "@/components/forms/Button";
import type { ApiError } from "@/lib/api/ApiError";
import { buildLoginRedirectPath } from "@/lib/auth/returnTo";
import { describeOfferStatus, formatMoney, offerDeadline, offerProductName } from "@/lib/offers/offerModel";
import type { OfferSummaryReadDTO } from "@/lib/offers/offerTypes";
import { formatOrderDate, formatOrderDateTime } from "@/lib/orders/orderFormat";

export interface OfferListProps {
  offers: readonly OfferSummaryReadDTO[];
  isLoading: boolean;
  error: ApiError | null;
  onRetry: () => void;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  onLoadMore: () => void;
  loadMoreFailed: boolean;
}

// #FVS-OFFERS-CUSTOMER-LIST (phase 6C). Presentational: each card shows only
// OfferSummaryRead's own fields (product, status, amount on the table, the
// deadline that applies now, opened date).
export function OfferList({ offers, isLoading, error, onRetry, hasNextPage, isFetchingNextPage, onLoadMore, loadMoreFailed }: OfferListProps) {
  if (isLoading) return <LoadingSpinner />;

  if (error) {
    if (error.kind === "http" && error.status === 401) {
      return (
        <div role="alert" className="flex flex-col items-start gap-3 rounded-md border-l-4 border-l-warning bg-warning-bg p-4">
          <p className="text-body text-text-primary">Your session has expired. Please sign in again to see your offers.</p>
          <Link href={buildLoginRedirectPath("/account/offers")} className="font-semibold text-brand-dark-green underline">
            Sign in
          </Link>
        </div>
      );
    }
    return (
      <div role="alert" className="flex flex-col items-start gap-3 rounded-md border-l-4 border-l-danger bg-danger-bg p-4">
        <p className="text-body text-text-primary">We couldn&apos;t load your offers. Please try again.</p>
        <Button type="button" variant="secondary" onClick={onRetry}>
          Try again
        </Button>
      </div>
    );
  }

  if (offers.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center">
        <p className="text-body text-text-secondary">You haven&apos;t made any offers yet. Offers can be made on STL files in the shop.</p>
        <Link href="/shop" className="font-semibold text-brand-dark-green underline">
          Browse the shop
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <ul className="flex flex-col gap-3">
        {offers.map((offer) => (
          <OfferCard key={offer.id} offer={offer} />
        ))}
      </ul>
      {loadMoreFailed && (
        <p role="alert" className="rounded-md border-l-4 border-l-danger bg-danger-bg p-3 text-body text-text-primary">
          We couldn&apos;t load more offers. Please try again.
        </p>
      )}
      {hasNextPage && (
        <Button type="button" variant="secondary" className="self-center" isLoading={isFetchingNextPage} onClick={onLoadMore}>
          Load more offers
        </Button>
      )}
    </div>
  );
}

function OfferCard({ offer }: { offer: OfferSummaryReadDTO }) {
  const status = describeOfferStatus(offer.status, "customer");
  const deadline = offerDeadline(offer);
  const name = offerProductName(offer.product.name);
  return (
    <li className="rounded-md border border-border-default bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 flex-col gap-1">
          <Link href={`/account/offers/${encodeURIComponent(offer.id)}`} className="break-words text-body font-semibold text-brand-dark-green underline">
            Offer on {name}
          </Link>
          <p className="text-caption text-text-secondary">Opened {formatOrderDate(offer.created_at)}</p>
        </div>
        <StatusBadge label={status.label} tone={status.tone} />
      </div>
      <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1 text-body text-text-primary tablet:grid-cols-2">
        <div className="flex gap-2">
          <dt className="text-text-secondary">{offer.agreed_amount ? "Agreed price" : "Amount on the table"}</dt>
          <dd className="font-semibold">{formatMoney(offer.agreed_amount ?? offer.current_amount)}</dd>
        </div>
        {deadline && (
          <div className="flex gap-2">
            <dt className="text-text-secondary">{deadline.kind === "checkout" ? "Check out by" : "Reply by"}</dt>
            <dd>
              <time dateTime={deadline.at}>{formatOrderDateTime(deadline.at)}</time>
            </dd>
          </div>
        )}
      </dl>
    </li>
  );
}
