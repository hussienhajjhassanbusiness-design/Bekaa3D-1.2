import Link from "next/link";
import {
  ACCOUNT_CARD,
  ACCOUNT_TERM,
  AccountErrorCard,
  AccountListSkeleton,
  AccountSessionCard,
  AccountThumb,
} from "@/components/account/accountUi";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { EmptyState } from "@/components/feedback/EmptyState";
import { Button } from "@/components/forms/Button";
import { Icon } from "@/components/ui/Icon";
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
//
// Batch 7 (Stitch C3 offer history, DERIVED to rows): one list card of
// rows with C3's 48px product thumb, the product as the row's single link
// (stretched over the row), the status as a text pill and the amount in
// C3's bold primary "Your offer" role. No KPI tiles, savings, seller quotes
// or per-row action buttons: the summary contract has no totals, and the
// moves live on the detail page, exactly as the server lists them there.
export function OfferList({
  offers,
  isLoading,
  error,
  onRetry,
  hasNextPage,
  isFetchingNextPage,
  onLoadMore,
  loadMoreFailed,
}: OfferListProps) {
  if (isLoading) return <AccountListSkeleton label="Loading your offers…" />;

  if (error) {
    if (error.kind === "http" && error.status === 401) {
      return (
        <AccountSessionCard
          message="Your session has expired. Please sign in again to see your offers."
          href={buildLoginRedirectPath("/account/offers")}
        />
      );
    }
    return <AccountErrorCard message="We couldn't load your offers. Please try again." onRetry={onRetry} />;
  }

  if (offers.length === 0) {
    return (
      <div className={ACCOUNT_CARD}>
        <EmptyState
          icon="sell"
          message="You haven't made any offers yet. Offers can be made on STL files in the shop."
          actionLabel="Browse the shop"
          actionHref="/shop"
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <ul className={`${ACCOUNT_CARD} divide-y divide-outline-variant/30 overflow-hidden`}>
        {offers.map((offer) => (
          <OfferRow key={offer.id} offer={offer} />
        ))}
      </ul>
      {loadMoreFailed && (
        <p
          role="alert"
          className="flex items-start gap-3 rounded-card border border-error/20 bg-error-container p-4 text-body-md text-on-error-container"
        >
          <Icon name="error" className="h-5 w-5 shrink-0 text-error" />
          We couldn&apos;t load more offers. Please try again.
        </p>
      )}
      {hasNextPage && (
        <Button
          type="button"
          variant="outline"
          className="self-center"
          isLoading={isFetchingNextPage}
          onClick={onLoadMore}
        >
          Load more offers
        </Button>
      )}
    </div>
  );
}

function OfferRow({ offer }: { offer: OfferSummaryReadDTO }) {
  const status = describeOfferStatus(offer.status, "customer");
  const deadline = offerDeadline(offer);
  const name = offerProductName(offer.product.name);
  return (
    <li className="group relative flex gap-4 p-5 transition-colors duration-200 ease-standard hover:bg-surface-container-low/60 motion-reduce:transition-none tablet:p-6">
      <AccountThumb src={offer.product.cover_image?.url} fallbackIcon="deployed-code" className="h-12 w-12" />
      <div className="flex min-w-0 flex-1 flex-col gap-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 flex-col gap-1">
            <Link
              href={`/account/offers/${encodeURIComponent(offer.id)}`}
              className="break-words text-title-sm text-on-surface after:absolute after:inset-0 after:content-[''] group-hover:text-primary group-hover:underline"
            >
              Offer on {name}
            </Link>
            <p className="font-label text-label-caps uppercase text-on-surface-variant">
              Opened {formatOrderDate(offer.created_at)}
            </p>
          </div>
          <StatusBadge label={status.label} tone={status.tone} />
        </div>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <dl className="grid min-w-0 flex-1 grid-cols-1 gap-x-6 gap-y-3 tablet:grid-cols-[repeat(2,minmax(0,max-content))]">
            <div className="min-w-0">
              <dt className={ACCOUNT_TERM}>{offer.agreed_amount ? "Agreed price" : "Amount on the table"}</dt>
              <dd className="mt-1 font-label text-title-sm font-bold text-primary">
                {formatMoney(offer.agreed_amount ?? offer.current_amount)}
              </dd>
            </div>
            {deadline && (
              <div className="min-w-0">
                <dt className={ACCOUNT_TERM}>{deadline.kind === "checkout" ? "Check out by" : "Reply by"}</dt>
                <dd className="mt-1 text-body-md text-on-surface">
                  <time dateTime={deadline.at}>{formatOrderDateTime(deadline.at)}</time>
                </dd>
              </div>
            )}
          </dl>
          <span
            aria-hidden="true"
            className="hidden items-center gap-1 font-label text-label-caps uppercase text-primary tablet:inline-flex"
          >
            View offer
            <Icon
              name="chevron-right"
              className="h-4 w-4 transition-transform duration-200 ease-standard group-hover:translate-x-1 motion-reduce:transition-none motion-reduce:group-hover:translate-x-0"
            />
          </span>
        </div>
      </div>
    </li>
  );
}
