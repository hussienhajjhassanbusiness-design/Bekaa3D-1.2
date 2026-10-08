import { AdminTable, type AdminTableColumn } from "@/components/admin/AdminTable";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { Button } from "@/components/forms/Button";
import type { RefundModel } from "@/lib/admin/refundModel";

export interface RefundQueueProps {
  refunds: readonly RefundModel[];
  isLoading?: boolean;
  onSelectRefund?: (refundId: string) => void;
}

const COLUMNS: readonly AdminTableColumn<RefundModel>[] = [
  {
    header: "Status",
    render: (refund) => <StatusBadge label={refund.statusLabel} tone={refund.isSettled ? "positive" : "neutral"} />,
  },
  {
    header: "Amount",
    render: (refund) => <PriceDisplay amountCents={refund.totalAmountCents} currency={refund.currency} />,
  },
  { header: "Method", render: (refund) => refund.settlementMethodLabel ?? "" },
  { header: "Order", render: (refund) => refund.linkedOrderDisplayId },
];

// #SHARED-ADMIN-TABLE reuse — mirrors AdminPaymentList's exact
// structure (FVS-032-IMPLEMENTATION-PLAN.md §0 evidence-tier
// decision). No second table implementation. Every value is
// plain/non-clickable — no admin refund-detail route exists yet to
// link to.
export function RefundQueue({ refunds, isLoading, onSelectRefund }: RefundQueueProps) {
  return (
    <AdminTable
      columns={COLUMNS}
      rows={refunds}
      getRowKey={(refund) => refund.id}
      isLoading={isLoading}
      rowActions={
        onSelectRefund
          ? (refund) => (
              <Button type="button" onClick={() => onSelectRefund(refund.id)}>
                View
              </Button>
            )
          : undefined
      }
    />
  );
}
