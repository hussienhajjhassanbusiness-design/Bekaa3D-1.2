import { StatusBadge } from "@/components/admin/StatusBadge";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import type { RefundModel } from "@/lib/admin/refundModel";

export interface RefundDetailProps {
  refund: RefundModel;
}

// #SECURITY-REFUND-SETTLEMENT-SEPARATION
//
// Admin-facing operational presentation only — RefundModel has no
// provider secret/raw webhook payload field, so none can be rendered
// here. Pending-vs-settled tone is driven by the explicit `isSettled`
// capability, never inferred from `statusLabel` text — a refund
// record can exist without money having moved.
export function RefundDetail({ refund }: RefundDetailProps) {
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-h3 font-bold text-text-primary">Refund {refund.id}</h2>
        <p className="text-caption text-text-secondary">Order {refund.linkedOrderDisplayId}</p>
      </div>

      <div className="flex items-center gap-3">
        <StatusBadge label={refund.statusLabel} tone={refund.isSettled ? "positive" : "neutral"} />
        <span className="font-semibold">
          <PriceDisplay amountCents={refund.totalAmountCents} currency={refund.currency} />
        </span>
      </div>

      {refund.settlementMethodLabel && (
        <p className="text-body text-text-primary">{refund.settlementMethodLabel}</p>
      )}

      {refund.lines && refund.lines.length > 0 && (
        <ul className="flex flex-col gap-2">
          {refund.lines.map((line) => (
            <li key={line.lineId} className="flex items-center justify-between gap-2">
              <span className="text-body text-text-primary">{line.productDisplayName}</span>
              <PriceDisplay amountCents={line.amountCents} currency={line.currency} />
            </li>
          ))}
        </ul>
      )}

      {refund.reason && <p className="text-body text-text-secondary">{refund.reason}</p>}
    </div>
  );
}
