import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import type { AdminOrderSummary } from "@/lib/admin/adminOrderModel";

export interface AdminOrderSummaryDisplayProps {
  summary: AdminOrderSummary;
}

// Extracted from OrderDetail — a second genuine reuse case
// (AdminOrderDetail) justifies pulling this out. Renders only the
// confirmed-concept fields present on the model, never fabricating a
// section for an absent one (#ARCHITECTURE-ORDER-SNAPSHOT-IMMUTABLE).
export function AdminOrderSummaryDisplay({ summary }: AdminOrderSummaryDisplayProps) {
  return (
    <dl className="flex flex-col gap-2">
      {summary.paymentStatusLabel && (
        <div className="flex items-center justify-between gap-2">
          <dt className="text-body text-text-secondary">Payment</dt>
          <dd className="text-body text-text-primary">{summary.paymentStatusLabel}</dd>
        </div>
      )}
      {summary.refundStatusLabel && (
        <div className="flex items-center justify-between gap-2">
          <dt className="text-body text-text-secondary">Refund</dt>
          <dd className="text-body text-text-primary">{summary.refundStatusLabel}</dd>
        </div>
      )}
      {summary.subtotalCents !== undefined && (
        <div className="flex items-center justify-between gap-2">
          <dt className="text-body text-text-secondary">Subtotal</dt>
          <dd>
            <PriceDisplay amountCents={summary.subtotalCents} currency={summary.currency} />
          </dd>
        </div>
      )}
      {summary.totalCents !== undefined && (
        <div className="flex items-center justify-between gap-2">
          <dt className="text-body font-semibold text-text-primary">Total</dt>
          <dd className="font-semibold">
            <PriceDisplay amountCents={summary.totalCents} currency={summary.currency} />
          </dd>
        </div>
      )}
    </dl>
  );
}
