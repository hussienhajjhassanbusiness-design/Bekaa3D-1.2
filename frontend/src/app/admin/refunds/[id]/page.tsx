"use client";

import { useParams } from "next/navigation";
import { RefundView } from "@/components/admin/payments/RefundView";
import { Alert } from "@/components/feedback/Alert";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { NotFoundContent } from "@/components/feedback/NotFoundContent";
import { isOrderId } from "@/lib/orders/orderModel";
import { useAdminRefund } from "@/lib/admin/payments/useAdminPayments";

// FVS-028 (phase 5I) — one refund, GET /api/v1/admin/refunds/{refund_id}.
export default function AdminRefundDetailPage() {
  const params = useParams<{ id: string }>();
  const refundId = typeof params.id === "string" ? params.id : "";
  const valid = isOrderId(refundId);
  const { data, isError, error } = useAdminRefund(refundId, { enabled: valid });

  if (!valid) return <NotFoundContent />;
  if (data) return <RefundView refund={data} />;
  if (isError) {
    if (error.kind === "http" && error.status === 404) return <NotFoundContent />;
    return <Alert variant="error" message="Couldn't load this refund. Please try again." />;
  }
  return <LoadingSpinner />;
}
