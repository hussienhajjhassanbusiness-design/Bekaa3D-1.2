"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useParams } from "next/navigation";
import { OrderDetailView } from "@/components/account/OrderDetailView";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { Button } from "@/components/forms/Button";
import { pickupOption } from "@/lib/checkout/checkoutEligibility";
import { adaptOrderDetail, isOrderId } from "@/lib/orders/orderModel";
import { classifyOrderError, ORDER_ERROR_COPY } from "@/lib/orders/orderErrors";
import { useMyOrder } from "@/lib/orders/useMyOrders";
import { usePublicSettings } from "@/lib/settings/usePublicSettings";

// FVS-029 (phase 5E) — one of the customer's own orders,
// GET /api/v1/me/orders/{order_id}. Protection comes from AccountLayout.
//
// #SECURITY-ORDER-IDOR-HIDING — the backend answers an unknown id and
// another customer's order with the same 404 NOT_FOUND. This page has one
// "Order not found" state for both (and for a malformed id, which is never
// sent to the API), so it reveals nothing the backend does not.
export default function AccountOrderDetailPage() {
  const params = useParams<{ id: string }>();
  const orderId = typeof params.id === "string" ? params.id : "";
  const validId = isOrderId(orderId);
  const query = useMyOrder(orderId, { enabled: validId });
  const settings = usePublicSettings();
  const order = useMemo(() => (query.data ? adaptOrderDetail(query.data) : null), [query.data]);

  if (!validId) {
    return <OrderNotFound />;
  }

  if (order) {
    return <OrderDetailView order={order} pickup={pickupOption(settings.data)} />;
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
