import { StatusBadge } from "@/components/admin/StatusBadge";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import type { OrderLineModel } from "@/lib/orders/orderModel";
import { describeLineStatus } from "@/lib/orders/orderStatus";
import { formatOrderDate } from "@/lib/orders/orderFormat";

export interface OrderLineItemProps {
  line: OrderLineModel;
  // True while the order is awaiting online payment: an STL is emailed only
  // once it is paid.
  awaitingPayment: boolean;
}

// #FVS029-ORDER-LINE (customer)
//
// The purchase-time snapshot exactly as the server returned it (name,
// image, unit price, quantity, line total). No product link and no live
// catalogue read: the snapshot never changes with the catalogue.
//
// #ADR-019 — an STL is emailed by an administrator: there is no download,
// no library and no entitlement, so this component has no download button
// or link of any kind. It states only what the line's own fields say
// (awaiting_delivery = paid, not yet emailed; fulfilled_at = when emailed).
// Receipt/problem timestamps are shown read-only; their actions are
// FVS-031 and are not mounted here.
export function OrderLineItem({ line, awaitingPayment }: OrderLineItemProps) {
  const status = describeLineStatus(line.fulfillmentStatus, line.productType);
  const isStl = line.productType === "stl";

  return (
    <div className="flex gap-3 border-b border-border-default py-3 last:border-b-0">
      <div className="h-16 w-16 shrink-0 overflow-hidden rounded-sm bg-neutral-100">
        {line.imageUrl && (
          // Plain <img>, matching CartLineItem/ProductCard: the media host is
          // not configured for next/image.
          // eslint-disable-next-line @next/next/no-img-element
          <img src={line.imageUrl} alt="" className="h-full w-full object-cover" />
        )}
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <p className="text-body font-semibold text-text-primary">{line.name}</p>
          <span className="font-semibold text-text-primary">
            <PriceDisplay amountCents={line.lineTotal.amountCents} currency={line.lineTotal.currency} />
          </span>
        </div>
        <p className="text-caption text-text-secondary">
          {isStl ? "STL file, sent by email" : "Physical item"} · Qty {line.quantity} ×{" "}
          <PriceDisplay amountCents={line.unitPrice.amountCents} currency={line.unitPrice.currency} />
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge label={status.label} tone={status.tone} />
        </div>
        <LineNotes line={line} awaitingPayment={awaitingPayment} />
      </div>
    </div>
  );
}

function LineNotes({ line, awaitingPayment }: OrderLineItemProps) {
  const notes: string[] = [];
  if (line.productType === "stl") {
    if (line.fulfilledAt) {
      notes.push(`Emailed to you on ${formatOrderDate(line.fulfilledAt)}.`);
    } else if (line.fulfillmentStatus === "awaiting_delivery") {
      notes.push("We'll email this file to you.");
    } else if (line.fulfillmentStatus === "pending" && awaitingPayment) {
      notes.push("We'll email this file to you once your payment is confirmed.");
    }
  } else {
    if (line.receiptConfirmedAt) notes.push(`You confirmed receipt on ${formatOrderDate(line.receiptConfirmedAt)}.`);
    if (line.problemReportedAt) notes.push(`You reported a problem on ${formatOrderDate(line.problemReportedAt)}.`);
  }
  if (line.cancelledAt) notes.push(`Cancelled on ${formatOrderDate(line.cancelledAt)}.`);

  if (notes.length === 0) return null;
  return (
    <ul className="flex flex-col gap-0.5 text-caption text-text-secondary">
      {notes.map((note) => (
        <li key={note}>{note}</li>
      ))}
    </ul>
  );
}
