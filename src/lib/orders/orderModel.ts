// #SECURITY-CUSTOMER-ORDER-PROJECTION
//
// Frontend-normalized, customer-visible shapes only — never a claim
// about the real OrderPage/OrderDetail response field names, which
// are unconfirmed (FVS-029-IMPLEMENTATION-PLAN.md §0/§1). None of
// these types has an internalNote/adminNote/staffId/
// providerRawPayload/manualConfirmReason field anywhere — that is
// the customer/admin boundary FVS-030 must respect by composition,
// never by adding such a field here.
//
// #ARCHITECTURE-ORDER-SNAPSHOT-IMMUTABLE — every price/display field
// below is a purchase-time snapshot a future adapter populates from
// the order projection itself. Nothing in this batch ever re-derives
// one from a live product/price lookup.
export interface OrderLineModel {
  id: string;
  productDisplayName: string;
  productType: "physical" | "stl";
  quantity: number;
  unitPriceCents: number;
  lineTotalCents: number;
  currency: string;
  // Presentation-ready text, never a claimed backend enum literal —
  // per-line status values are unconfirmed.
  statusLabel: string;
  thumbnailSrc?: string;
}

// Payment/refund are optional presentation labels only — never a
// claimed amount/reason/provider-reference shape, since none is
// confirmed. Address/zone snapshots are deliberately absent entirely
// this batch (plan §0) rather than guessed. No `shippingCents` field:
// ADR-024 means nothing is ever charged for shipping on this site.
export interface OrderSummaryModel {
  currency: string;
  paymentStatusLabel?: string;
  refundStatusLabel?: string;
  subtotalCents?: number;
  totalCents?: number;
}

export interface OrderDetailModel {
  id: string;
  displayDate: string;
  statusLabel: string;
  lines: readonly OrderLineModel[];
  summary: OrderSummaryModel;
}

export interface OrderListItemModel {
  id: string;
  displayDate: string;
  statusLabel: string;
  totalCents?: number;
  currency?: string;
}

// Normalized, in-memory filter state — deliberately NOT bound to any
// URL query-parameter name (plan §6: no literal example exists for
// /account/orders, unlike FVS-013's own shop precedent).
export interface OrderListFilters {
  status: string | null;
  dateFrom: string | null;
  dateTo: string | null;
  cursor: string | null;
}
