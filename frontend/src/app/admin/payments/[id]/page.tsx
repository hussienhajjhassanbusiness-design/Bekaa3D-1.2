"use client";

import { useParams } from "next/navigation";
import { AdminPaymentView } from "@/components/admin/payments/AdminPaymentView";
import { Alert } from "@/components/feedback/Alert";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { NotFoundContent } from "@/components/feedback/NotFoundContent";
import { isOrderId } from "@/lib/orders/orderModel";
import { useAdminPayment } from "@/lib/admin/payments/useAdminPayments";

// FVS-028 (phase 5I) — one payment, GET /api/v1/admin/payments/{payment_id}.
// A non-UUID id is never sent and reads as not found.
export default function AdminPaymentDetailPage() {
  const params = useParams<{ id: string }>();
  const paymentId = typeof params.id === "string" ? params.id : "";
  const valid = isOrderId(paymentId);
  const { data, isError, error } = useAdminPayment(paymentId, { enabled: valid });

  if (!valid) return <NotFoundContent />;
  if (data) return <AdminPaymentView detail={data} />;
  if (isError) {
    if (error.kind === "http" && error.status === 404) return <NotFoundContent />;
    return <Alert variant="error" message="Couldn't load this payment. Please try again." />;
  }
  return <LoadingSpinner />;
}
