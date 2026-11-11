import Link from "next/link";
import { Button } from "@/components/forms/Button";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import type { OrderSummaryModel } from "@/lib/orders/orderModel";
import { describeOrderStatus } from "@/lib/orders/orderStatus";
import { classifyOrderError, ORDER_ERROR_COPY } from "@/lib/orders/orderErrors";
import { formatOrderDate, fulfillmentLabel, paymentMethodLabel } from "@/lib/orders/orderFormat";

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
    return <LoadingSpinner />;
  }

  if (error) {
    if (classifyOrderError(error) === "auth") {
      return (
        <div role="alert" className="flex flex-col items-start gap-3 rounded-md border-l-4 border-l-warning bg-warning-bg p-4">
          <p className="text-body text-text-primary">{ORDER_ERROR_COPY.sessionExpired}</p>
          <Link href={SIGN_IN_HREF} className="font-semibold text-brand-dark-green underline">
            Sign in
          </Link>
        </div>
      );
    }
    return (
      <div role="alert" className="flex flex-col items-start gap-3 rounded-md border-l-4 border-l-danger bg-danger-bg p-4">
        <p className="text-body text-text-primary">{ORDER_ERROR_COPY.listFailed}</p>
        <Button type="button" variant="secondary" onClick={onRetry}>
          Try again
        </Button>
      </div>
    );
  }

  if (orders.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center">
        <p className="text-body text-text-secondary">You haven&apos;t placed any orders yet.</p>
        <Link href="/shop" className="font-semibold text-brand-dark-green underline">
          Browse the shop
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <ul className="flex flex-col gap-3">
        {orders.map((order) => (
          <OrderCard key={order.id} order={order} />
        ))}
      </ul>

      {loadMoreFailed && (
        <p role="alert" className="rounded-md border-l-4 border-l-danger bg-danger-bg p-3 text-body text-text-primary">
          {ORDER_ERROR_COPY.loadMoreFailed}
        </p>
      )}

      {hasNextPage && (
        <Button
          type="button"
          variant="secondary"
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

function OrderCard({ order }: { order: OrderSummaryModel }) {
  const status = describeOrderStatus(order.status);
  return (
    <li className="rounded-md border border-border-default bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex flex-col gap-1">
          <Link
            href={`/account/orders/${encodeURIComponent(order.id)}`}
            className="text-body font-semibold text-brand-dark-green underline"
          >
            Order {order.orderNumber}
          </Link>
          <p className="text-caption text-text-secondary">Placed {formatOrderDate(order.placedAt)}</p>
        </div>
        <StatusBadge label={status.label} tone={status.tone} />
      </div>

      <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1 text-body text-text-primary tablet:grid-cols-3">
        <div className="flex gap-2">
          <dt className="text-text-secondary">Total</dt>
          <dd className="font-semibold">
            <PriceDisplay amountCents={order.total.amountCents} currency={order.total.currency} />
          </dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-text-secondary">Payment</dt>
          <dd>{paymentMethodLabel(order.paymentMethod)}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-text-secondary">Fulfillment</dt>
          <dd>{fulfillmentLabel(order.fulfillmentMethod)}</dd>
        </div>
      </dl>

      {order.paymentDue && order.amountDue && (
        <p className="mt-2 text-body text-text-primary">
          Payment due in cash:{" "}
          <span className="font-semibold">
            <PriceDisplay amountCents={order.amountDue.amountCents} currency={order.amountDue.currency} />
          </span>
        </p>
      )}
    </li>
  );
}
