import type { StatusBadgeTone } from "@/components/admin/StatusBadge";
import type { ProductType } from "@/lib/catalog/productTypes";

// #FVS029-STATUS-PRESENTATION
//
// Frontend-owned labels for the backend's order, payment and line enums.
// Every lookup is an own-property check on a fixed table, so a value the
// backend adds later (or an Object.prototype key) can never crash a render
// or be echoed verbatim: it degrades to UNKNOWN. Nothing here branches on
// backend English text, and no label claims more than the value means
// (e.g. `pending` online payment is "Awaiting payment", never "Paid").

export interface StatusDescriptor {
  label: string;
  tone: StatusBadgeTone;
}

const UNKNOWN: StatusDescriptor = { label: "Status unavailable", tone: "neutral" };

function lookup<T>(table: Readonly<Record<string, T>>, value: string): T | undefined {
  return Object.prototype.hasOwnProperty.call(table, value) ? table[value] : undefined;
}

const ORDER_STATUS: Readonly<Record<string, StatusDescriptor>> = {
  pending_payment: { label: "Awaiting payment", tone: "warning" },
  in_progress: { label: "In progress", tone: "neutral" },
  completed: { label: "Completed", tone: "positive" },
  partially_refunded: { label: "Partially refunded", tone: "neutral" },
  refunded: { label: "Refunded", tone: "neutral" },
  cancelled: { label: "Cancelled", tone: "negative" },
};

// OrderPaymentRead.status (backend PaymentStatus).
const PAYMENT_STATUS: Readonly<Record<string, StatusDescriptor>> = {
  pending: { label: "Awaiting payment", tone: "warning" },
  processing: { label: "Payment processing", tone: "warning" },
  paid: { label: "Paid", tone: "positive" },
  partially_refunded: { label: "Partially refunded", tone: "neutral" },
  refunded: { label: "Refunded", tone: "neutral" },
  failed: { label: "Payment failed", tone: "negative" },
  expired: { label: "Payment expired", tone: "negative" },
};

// OrderItemStatus. `pending` covers printing too ("Received", per
// docs/order-history.md). STL lines are emailed by hand (ADR-019): there is
// no download, so `delivered` on an STL line is "Emailed".
const LINE_STATUS: Readonly<Record<string, StatusDescriptor>> = {
  pending: { label: "Received", tone: "neutral" },
  awaiting_delivery: { label: "Paid, not yet emailed", tone: "neutral" },
  in_production: { label: "In production", tone: "neutral" },
  ready_to_ship: { label: "Ready to ship", tone: "neutral" },
  shipped: { label: "Shipped", tone: "neutral" },
  delivered: { label: "Delivered", tone: "positive" },
  returned: { label: "Returned", tone: "warning" },
  ready_for_pickup: { label: "Ready for pickup", tone: "neutral" },
  picked_up: { label: "Picked up", tone: "positive" },
  cancelled: { label: "Cancelled", tone: "negative" },
  refunded: { label: "Refunded", tone: "neutral" },
};

const STL_LINE_OVERRIDES: Readonly<Record<string, StatusDescriptor>> = {
  delivered: { label: "Emailed", tone: "positive" },
};

export function describeOrderStatus(status: string): StatusDescriptor {
  return lookup(ORDER_STATUS, status) ?? UNKNOWN;
}

export function describePaymentStatus(status: string): StatusDescriptor {
  return lookup(PAYMENT_STATUS, status) ?? UNKNOWN;
}

export function describeLineStatus(status: string, productType: ProductType | string): StatusDescriptor {
  if (productType === "stl") {
    const override = lookup(STL_LINE_OVERRIDES, status);
    if (override) return override;
  }
  return lookup(LINE_STATUS, status) ?? UNKNOWN;
}

// A status_history entry: order-level when `lineProductType` is null.
export function describeHistoryStatus(status: string, lineProductType: ProductType | string | null): string {
  return lineProductType === null
    ? describeOrderStatus(status).label
    : describeLineStatus(status, lineProductType).label;
}

const REFUND_KIND: Readonly<Record<string, string>> = {
  admin: "Refund",
  cancellation: "Cancellation refund",
  late_capture: "Late payment refund",
};

const REFUND_STATUS: Readonly<Record<string, string>> = {
  processing: "Processing",
  refunded: "Refunded",
};

export function describeRefundKind(kind: string): string {
  return lookup(REFUND_KIND, kind) ?? "Refund";
}

export function describeRefundStatus(status: string): string {
  return lookup(REFUND_STATUS, status) ?? UNKNOWN.label;
}
