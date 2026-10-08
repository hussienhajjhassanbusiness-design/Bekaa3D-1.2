import type { OrderLineModel, OrderSummaryModel } from "@/lib/orders/orderModel";

// #SECURITY-SERVER-FULFILLMENT-STATE-MACHINE
//
// A frontend-normalized, server-authoritative action — never derived
// from status locally. The frontend renders exactly the actions it
// is given (FVS-030-IMPLEMENTATION-PLAN.md §0/T01); `id`/`label` are
// not claimed backend field names.
export interface TransitionAffordance {
  id: string;
  label: string;
  requiresConfirmation: boolean;
}

// #ARCHITECTURE-ADMIN-ORDER-PROJECTION
//
// Reuses FVS-029's OrderLineModel directly via extension — never a
// forked copy. `availableActions` is the one admin-only layered
// addition; an empty array is valid (a digital/STL line may
// legitimately have no legal transitions).
export interface AdminOrderLineModel extends OrderLineModel {
  availableActions: readonly TransitionAffordance[];
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
  summary: OrderSummaryModel;
  internalNote: string;
}
