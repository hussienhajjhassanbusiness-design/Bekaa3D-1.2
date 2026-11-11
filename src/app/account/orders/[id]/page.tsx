"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useParams } from "next/navigation";
import { OrderCustomerActions } from "@/components/account/OrderCustomerActions";
import { OrderDetailView } from "@/components/account/OrderDetailView";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { Button } from "@/components/forms/Button";
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
        <div role="alert" className="flex flex-col items-start gap-3 rounded-md border-l-4 border-l-warning bg-warning-bg p-4">
          <p className="text-body text-text-primary">{ORDER_ERROR_COPY.sessionExpired}</p>
          <Link
            href={`/login?returnTo=${encodeURIComponent(`/account/orders/${orderId}`)}`}
            className="font-semibold text-brand-dark-green underline"
          >
            Sign in
          </Link>
        </div>
      );
    }
    return (
      <div role="alert" className="flex flex-col items-start gap-3 rounded-md border-l-4 border-l-danger bg-danger-bg p-4">
        <p className="text-body text-text-primary">{ORDER_ERROR_COPY.detailFailed}</p>
        <Button type="button" variant="secondary" onClick={() => void query.refetch()}>
          Try again
        </Button>
      </div>
    );
  }

  return <LoadingSpinner />;
}

function OrderNotFound() {
  return (
    <div className="flex flex-col items-start gap-3">
      <h1 className="text-h1 font-bold text-text-primary">{ORDER_ERROR_COPY.notFoundTitle}</h1>
      <p className="text-body text-text-secondary">{ORDER_ERROR_COPY.notFoundBody}</p>
      <Link href="/account/orders" className="font-semibold text-brand-dark-green underline">
        View your orders
      </Link>
    </div>
  );
}
