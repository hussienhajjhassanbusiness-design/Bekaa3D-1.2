import type { OrderActionAffordance } from "@/lib/orders/orderActionModel";

// #FVS030-LEGACY-SPECULATIVE (phase 5E)
//
// These two shapes were FVS-029's pre-contract customer models. The real
// customer order domain (src/lib/orders/orderModel.ts, phase 5E) replaced
// them; they live on here ONLY because the still-unmounted admin order
// components were built on them. They are speculative label-only shapes,
// NOT the real AdminOrderDetail contract: the admin-orders phase must
// rebuild these against `GET /api/v1/admin/orders/{id}` (AdminOrderDetail,
// AdminOrderLineRead) rather than extend them.
export interface AdminOrderLineBase {
  id: string;
  productDisplayName: string;
  productType: "physical" | "stl";
  quantity: number;
  unitPriceCents: number;
  lineTotalCents: number;
  currency: string;
  statusLabel: string;
  thumbnailSrc?: string;
}

export interface AdminOrderSummary {
  currency: string;
  paymentStatusLabel?: string;
  refundStatusLabel?: string;
  subtotalCents?: number;
  totalCents?: number;
}

// #SECURITY-SERVER-FULFILLMENT-STATE-MACHINE
//
// A frontend-normalized, server-authoritative action — never derived
// from status locally. The frontend renders exactly the actions it
// is given (FVS-030-IMPLEMENTATION-PLAN.md §0/T01); `id`/`label` are
// not claimed backend field names.
//
// Re-exported from the neutral `orderActionModel` module (FVS-031
// §1) so customer-side code can consume the identical shape without
// importing from `admin/` — this alias keeps every existing import
// of `TransitionAffordance` from this module working unchanged.
export type TransitionAffordance = OrderActionAffordance;

// #ARCHITECTURE-ADMIN-ORDER-PROJECTION
//
// Reuses FVS-029's OrderLineModel directly via extension — never a
// forked copy. `availableActions` is the one admin-only layered
// addition; an empty array is valid (a digital/STL line may
// legitimately have no legal transitions).
//
// `adminCancelAction`/`refundObligationMessage` (FVS-031) are
// additive and optional: admin cancellation is its own endpoint per
// VS-025, distinct from the transition endpoint `availableActions`
// models, so it is never folded into that array
// (#SECURITY-SERVER-CANCELLATION-AUTHORITY). Neither field claims a
// real backend name or computes a refund amount
// (#ARCHITECTURE-REFUND-OBLIGATION-SERVER-OWNED) — both are only
// ever caller-supplied.
export interface AdminOrderLineModel extends AdminOrderLineBase {
  availableActions: readonly TransitionAffordance[];
  adminCancelAction?: OrderActionAffordance | null;
  refundObligationMessage?: string;
}

// #SECURITY-INTERNAL-NOTE-BOUNDARY
//
// Reuses FVS-029's OrderSummaryModel directly, unmodified.
// `internalNote` is the one admin-only field here — it must NEVER be
// added to any FVS-029 customer-facing type (OrderLineModel,
// OrderDetailModel, OrderLineItemProps, OrderDetailProps); see this
// module's own test file for the cross-slice regression proof.
export interface AdminOrderModel {
  id: string;
  displayDate: string;
  statusLabel: string;
  lines: readonly AdminOrderLineModel[];
  summary: AdminOrderSummary;
  internalNote: string;
}
