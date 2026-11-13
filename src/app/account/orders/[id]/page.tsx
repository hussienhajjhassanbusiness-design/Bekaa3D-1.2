"use client";

import { useMemo } from "react";
import { useParams } from "next/navigation";
import { OrderCustomerActions } from "@/components/account/OrderCustomerActions";
import { OrderDetailView } from "@/components/account/OrderDetailView";
import {
  ACCOUNT_CARD,
  AccountErrorCard,
  AccountListSkeleton,
  AccountSessionCard,
} from "@/components/account/accountUi";
import { EmptyState } from "@/components/feedback/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { pickupOption } from "@/lib/checkout/checkoutEligibility";
import { adaptOrderDetail, isOrderId } from "@/lib/orders/orderModel";
import { classifyOrderError, ORDER_ERROR_COPY } from "@/lib/orders/orderErrors";
import { usePolledOrder } from "@/lib/orders/usePolledOrder";
import { useRetryPayment } from "@/lib/orders/useRetryPayment";
import { usePublicSettings } from "@/lib/settings/usePublicSettings";

// FVS-029 (phase 5E) — one of the customer's own orders,
// GET /api/v1/me/orders/{order_id}. Protection comes from AccountLayout.
//
// #SECURITY-ORDER-IDOR-HIDING — the backend answers an unknown id and
// another customer's order with the same 404 NOT_FOUND. This page has one
// "Order not found" state for both (and for a malformed id, which is never
// sent to the API), so it reveals nothing the backend does not.
//
// FVS-027 (phase 5F) — this page is the customer's payment-status surface.
// It reads the canonical orderKeys.detail(id) query through
// usePolledOrder (bounded re-reads only while the server reports a live
// payment attempt) and owns the one "Retry payment" flow
// (useRetryPayment). No payment state is ever set locally.
//
// FVS-031 (phase 5G) — the customer's cancel / confirm receipt / report a
// problem actions (OrderCustomerActions), offered from the same canonical
// order and writing back only into it.
export default function AccountOrderDetailPage() {
  const params = useParams<{ id: string }>();
  const orderId = typeof params.id === "string" ? params.id : "";
  const validId = isOrderId(orderId);
  const { query, polling, timedOut, checkAgain } = usePolledOrder(orderId, { enabled: validId });
  const retry = useRetryPayment(orderId);
  const settings = usePublicSettings();
  const order = useMemo(() => (query.data ? adaptOrderDetail(query.data) : null), [query.data]);

  if (!validId) {
    return <OrderNotFound />;
  }

  if (order) {
    return (
      <OrderDetailView
        order={order}
        pickup={pickupOption(settings.data)}
        customerActions={<OrderCustomerActions order={order} />}
        paymentControls={{
          polling,
          timedOut,
          onCheckAgain: checkAgain,
          onHoldElapsed: () => void query.refetch(),
          retry: { state: retry.state, onRetry: () => void retry.start(), onResume: retry.resume },
        }}
      />
    );
  }

  if (query.isError) {
    const kind = classifyOrderError(query.error);
    if (kind === "not-found") {
      return <OrderNotFound />;
    }
    if (kind === "auth") {
      return (
        <>
          <PageHeader eyebrow="Order details" title="Order" />
          <AccountSessionCard
            message={ORDER_ERROR_COPY.sessionExpired}
            href={`/login?returnTo=${encodeURIComponent(`/account/orders/${orderId}`)}`}
          />
        </>
      );
    }
    return (
      <>
        <PageHeader eyebrow="Order details" title="Order" />
        <AccountErrorCard message={ORDER_ERROR_COPY.detailFailed} onRetry={() => void query.refetch()} />
      </>
    );
  }

  return (
    <>
      <PageHeader eyebrow="Order details" title="Order" />
      <AccountListSkeleton label="Loading this order…" rows={2} />
    </>
  );
}

// Batch 7: the page keeps one h1 in every state. Not found reuses the §49
// empty state; the copy (which reveals nothing about ownership) is unchanged.
function OrderNotFound() {
  return (
    <>
      <PageHeader eyebrow="Order details" title={ORDER_ERROR_COPY.notFoundTitle} />
      <div className={ACCOUNT_CARD}>
        <EmptyState
          icon="receipt-long"
          message={ORDER_ERROR_COPY.notFoundBody}
          actionLabel="View your orders"
          actionHref="/account/orders"
        />
      </div>
    </>
  );
}
