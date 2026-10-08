import { StatusBadge } from "@/components/admin/StatusBadge";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import type { OrderLineModel } from "@/lib/orders/orderModel";

export interface OrderLineItemProps {
  line: OrderLineModel;
}

// #ARCHITECTURE-CUSTOMER-ADMIN-ORDER-BOUNDARY
//
// The customer-visible shared primitive FVS-030 must compose around
// (AdminOrderLine = OrderLineItem + admin controls, rendered
// separately) — never modified to add admin fields. Renders only
// supplied immutable snapshot data
// (#ARCHITECTURE-ORDER-SNAPSHOT-IMMUTABLE): no fetch, no product
// link (no confirmed product identifier/link exists for a purchased
// snapshot), no internal note or admin-action prop of any kind.
// Per-line status uses a uniform neutral StatusBadge tone — per-line
// status literals are unconfirmed, so no severity semantics are
// guessed; the label itself is always visible text, never color-only.
export function OrderLineItem({ line }: OrderLineItemProps) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border-default py-3">
      <div>
        <p className="text-body text-text-primary">{line.productDisplayName}</p>
        <p className="text-caption text-text-secondary">Qty: {line.quantity}</p>
      </div>
      <div className="flex items-center gap-3">
        <StatusBadge label={line.statusLabel} tone="neutral" />
        <PriceDisplay amountCents={line.lineTotalCents} currency={line.currency} />
      </div>
    </div>
  );
}
