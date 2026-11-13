import Link from "next/link";
import { Button } from "@/components/forms/Button";
import { EmptyState } from "@/components/feedback/EmptyState";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { Icon } from "@/components/ui/Icon";
import type { OrderSummaryModel } from "@/lib/orders/orderModel";
import { describeOrderStatus } from "@/lib/orders/orderStatus";
import { classifyOrderError, ORDER_ERROR_COPY } from "@/lib/orders/orderErrors";
import { formatOrderDate, fulfillmentLabel, paymentMethodLabel } from "@/lib/orders/orderFormat";
import { ACCOUNT_CARD, ACCOUNT_TERM, AccountErrorCard, AccountListSkeleton, AccountSessionCard } from "./accountUi";

export interface OrderHistoryListProps {
  orders: readonly OrderSummaryModel[];
  isLoading: boolean;
  // The first-page failure, if any (a later page's failure is loadMoreFailed).
  error: unknown;
  onRetry: () => void;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  onLoadMore: () => void;
  loadMoreFailed: boolean;
}

const SIGN_IN_HREF = `/login?returnTo=${encodeURIComponent("/account/orders")}`;

// #FVS029-ORDER-HISTORY
//
// Presentational. Each card shows only OrderSummaryRead's own fields:
// number, placed date, order status, payment method, fulfillment method,
// total and (an unpaid cash order only) the amount due. The list response
// carries no lines, so there is no line summary here; it is on the detail
// page. Nothing claims "paid": the summary has no payment status.
//
// Batch 7 (Stitch C2 order history, DERIVED to rows): the C2 table becomes
// one list card of rows so it never needs horizontal scrolling inside the
// account column. Each row keeps exactly one link (the order number, mono
// primary like C2's ORDER ID), stretched over the row so the whole row is
// clickable; C2's "View details" is a decorative cue inside that link's
// hit area, not a second control. No tracking, ETA, thumbnails or payment
// status: the summary contract has none.
export function OrderHistoryList({
  orders,
  isLoading,
  error,
  onRetry,
  hasNextPage,
  isFetchingNextPage,
  onLoadMore,
  loadMoreFailed,
}: OrderHistoryListProps) {
  if (isLoading) {
    return <AccountListSkeleton label="Loading your orders…" />;
  }

  if (error) {
    if (classifyOrderError(error) === "auth") {
      return <AccountSessionCard message={ORDER_ERROR_COPY.sessionExpired} href={SIGN_IN_HREF} />;
    }
    return <AccountErrorCard message={ORDER_ERROR_COPY.listFailed} onRetry={onRetry} />;
  }

  if (orders.length === 0) {
    return (
      <div className={ACCOUNT_CARD}>
        <EmptyState
          icon="shopping-bag"
          message="You haven't placed any orders yet."
          actionLabel="Browse the shop"
          actionHref="/shop"
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <ul className={`${ACCOUNT_CARD} divide-y divide-outline-variant/30 overflow-hidden`}>
        {orders.map((order) => (
          <OrderRow key={order.id} order={order} />
        ))}
      </ul>

      {loadMoreFailed && (
        <p
          role="alert"
          className="flex items-start gap-3 rounded-card border border-error/20 bg-error-container p-4 text-body-md text-on-error-container"
        >
          <Icon name="error" className="h-5 w-5 shrink-0 text-error" />
          {ORDER_ERROR_COPY.loadMoreFailed}
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
          Load more orders
        </Button>
      )}
    </div>
  );
}

function OrderRow({ order }: { order: OrderSummaryModel }) {
  const status = describeOrderStatus(order.status);
  return (
    <li className="group relative flex flex-col gap-4 p-5 transition-colors duration-200 ease-standard hover:bg-surface-container-low/60 motion-reduce:transition-none tablet:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <Link
            href={`/account/orders/${encodeURIComponent(order.id)}`}
            className="break-all font-label text-title-sm font-bold text-primary after:absolute after:inset-0 after:content-[''] group-hover:underline"
          >
            Order {order.orderNumber}
          </Link>
          <p className="font-label text-label-caps uppercase text-on-surface-variant">
            Placed {formatOrderDate(order.placedAt)}
          </p>
        </div>
        <StatusBadge label={status.label} tone={status.tone} />
      </div>

      <div className="flex flex-wrap items-end justify-between gap-4">
        <dl className="grid min-w-0 flex-1 grid-cols-2 gap-x-6 gap-y-3 tablet:grid-cols-[repeat(3,minmax(0,max-content))]">
          <div className="min-w-0">
            <dt className={ACCOUNT_TERM}>Total</dt>
            <dd className="mt-1 font-label text-title-sm font-bold text-on-surface">
              <PriceDisplay amountCents={order.total.amountCents} currency={order.total.currency} />
            </dd>
          </div>
          <div className="min-w-0">
            <dt className={ACCOUNT_TERM}>Payment</dt>
            <dd className="mt-1 text-body-md text-on-surface">{paymentMethodLabel(order.paymentMethod)}</dd>
          </div>
          <div className="min-w-0">
            <dt className={ACCOUNT_TERM}>Fulfillment</dt>
            <dd className="mt-1 text-body-md text-on-surface">{fulfillmentLabel(order.fulfillmentMethod)}</dd>
          </div>
        </dl>
        <span
          aria-hidden="true"
          className="hidden items-center gap-1 font-label text-label-caps uppercase text-primary tablet:inline-flex"
        >
          View details
          <Icon
            name="chevron-right"
            className="h-4 w-4 transition-transform duration-200 ease-standard group-hover:translate-x-1 motion-reduce:transition-none motion-reduce:group-hover:translate-x-0"
          />
        </span>
      </div>

      {order.paymentDue && order.amountDue && (
        <p className="flex items-start gap-2 self-start rounded-control border border-info-outline bg-info-container px-3 py-2 text-body text-on-info-container">
          <Icon name="payments" className="mt-0.5 h-4 w-4 shrink-0 text-info" />
          <span>
            Payment due in cash:{" "}
            <span className="font-semibold">
              <PriceDisplay amountCents={order.amountDue.amountCents} currency={order.amountDue.currency} />
            </span>
          </span>
        </p>
      )}
    </li>
  );
}
