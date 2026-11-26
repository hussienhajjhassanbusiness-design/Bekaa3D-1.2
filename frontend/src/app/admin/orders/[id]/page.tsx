"use client";

import { useParams } from "next/navigation";
import { AdminOrderView } from "@/components/admin/orders/AdminOrderView";
import { Alert } from "@/components/feedback/Alert";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { NotFoundContent } from "@/components/feedback/NotFoundContent";
import { Button } from "@/components/forms/Button";
import { isOrderId } from "@/lib/orders/orderModel";
import { useAdminOrder } from "@/lib/admin/orders/useAdminOrders";

// FVS-030 (phase 5H) — one order, GET /api/v1/admin/orders/{order_id}.
// The canonical adminOrderKeys.detail(id) entry: every write on this page
// replaces it with the server's own AdminOrderDetail. A non-UUID id is
// never sent (the backend would answer 422) and reads as not found.
export default function AdminOrderDetailPage() {
  const params = useParams<{ id: string }>();
  const orderId = typeof params.id === "string" ? params.id : "";
  const valid = isOrderId(orderId);
  const { data, isError, error, refetch } = useAdminOrder(orderId, { enabled: valid });

  if (!valid) return <NotFoundContent />;
  if (data) return <AdminOrderView order={data} />;
  if (isError) {
    if (error.kind === "http" && error.status === 404) return <NotFoundContent />;
    return (
      <div className="flex flex-col items-start gap-3">
        <Alert variant="error" message="Couldn't load this order. Please try again." />
        <Button type="button" variant="secondary" onClick={() => void refetch()}>
          Try again
        </Button>
      </div>
    );
  }
  return <LoadingSpinner />;
}
