import type { PriceRead, ProductType } from "@/lib/catalog/productTypes";
import type { FulfillmentMethod, OrderItemStatus, OrderSource, OrderStatus, PaymentMethod } from "@/lib/orders/orderTypes";

// #FVS030-ADMIN-ORDER-WIRE-CONTRACT (phase 5H)
//
// Raw wire shapes for the administrator's order routes, transcribed from
// the running backend 2dfb27b (`/openapi.json` AdminOrderPage,
// AdminOrderSummaryRead, AdminOrderDetail, AdminOrderLineRead,
// AvailableActionRead, AdminOrderPaymentRead, AdminHistoryRead,
// AdminOrderRefundRead, AdminOrderChargebackRead, AdminRefundBalanceRead,
// OrderItemTransitionRequest, CashHandoverRequest, AdminOrderUpdate,
// AdminOrderCancelRequest, StlDeliveryPage, StlDeliveryRead) and the
// implementation (fulfillment/api/admin_orders.py, item_transition.py,
// stl_deliveries.py, admin_order_schemas.py; ordering/domain/
// line_transitions.py, handover.py). snake_case on purpose: only the
// admin order adapter and pages read these.
//
// Access: administrator with completed MFA (401 MFA_REQUIRED otherwise);
// a customer gets 404 from the admin boundary. Writes need X-CSRF-Token.
// There is NO version / If-Match concurrency on these routes: every write
// re-checks the line's state under the server's lock and refuses with 409.

export type CancelReason = "refused" | "no_show" | "other";

export interface AdminOrderSummaryReadDTO {
  id: string;
  order_number: string;
  customer_id: string;
  customer_email: string;
  status: OrderStatus;
  fulfillment_method: FulfillmentMethod | null;
  payment_method: PaymentMethod;
  // An unpaid cash order: the "cash due" view.
  payment_due: boolean;
  amount_due: PriceRead | null;
  total: PriceRead;
  estimated_dispatch_at: string | null;
  placed_at: string;
}

// Newest first; never an unpaid online order. Keyset cursor, no total.
export interface AdminOrderPageDTO {
  items: AdminOrderSummaryReadDTO[];
  next_cursor: string | null;
}

// GET /api/v1/admin/orders query. `status=pending_payment` is a 422
// (unpaid online orders are never in the queue). limit 1-100, default 25.
export interface AdminOrdersQueryParams {
  status?: Exclude<OrderStatus, "pending_payment">;
  fulfillment_method?: FulfillmentMethod;
  payment_method?: PaymentMethod;
  payment_due?: boolean;
  order_number?: string;
  cursor?: string;
  limit?: number;
}

export interface AvailableActionReadDTO {
  target_status: OrderItemStatus;
  // Empty: the transition takes no reason; otherwise one is required.
  cancel_reasons: CancelReason[];
}

export interface AdminOrderLineReadDTO {
  id: string;
  product_id: string;
  product_type: ProductType;
  name: string;
  image_url: string | null;
  unit_price: PriceRead;
  quantity: number;
  line_total: PriceRead;
  // The real state, never masked (in_production included).
  fulfillment_status: OrderItemStatus;
  fulfilled_at: string | null;
  delivered_by: string | null;
  cancelled_at: string | null;
  cancel_reason: CancelReason | null;
  offer_id: string | null;
  lead_time_days: number | null;
  batch_size: number | null;
  receipt_confirmed_at: string | null;
  problem_reported_at: string | null;
  // What the transition endpoint accepts now; it re-checks (ADR-025).
  available_actions: AvailableActionReadDTO[];
}

export interface AdminDeliveryAddressReadDTO {
  recipient_name: string | null;
  governorate: string | null;
  city: string | null;
  area: string | null;
  street: string | null;
  landmark_notes: string | null;
}

export interface AdminOrderPaymentReadDTO {
  id: string;
  provider: string;
  // A plain string (backend PaymentStatus).
  status: string;
  amount: PriceRead;
  initiated_at: string;
  verified_at: string | null;
  late_captured_at: string | null;
  // Cash: the administrator who recorded it.
  recorded_by: string | null;
}

export interface AdminHistoryReadDTO {
  order_item_id: string | null;
  from_status: string | null;
  to_status: string;
  // Null: the system.
  actor_user_id: string | null;
  reason: string | null;
  at: string;
}

export interface AdminOrderRefundReadDTO {
  id: string;
  kind: string;
  status: string;
  owed: boolean;
  amount: PriceRead;
  created_at: string;
}

export interface AdminOrderChargebackReadDTO {
  id: string;
  payment_id: string;
  charged: PriceRead;
  applied_cents: number;
  excess_cents: number;
  received_at: string;
}

export interface AdminRefundBalanceReadDTO {
  lines: { order_item_id: string; balance_cents: number }[];
  payment_cents: number;
}

export interface AdminOrderDetailDTO {
  id: string;
  order_number: string;
  source: OrderSource;
  customer_id: string;
  customer_email: string;
  status: OrderStatus;
  fulfillment_method: FulfillmentMethod | null;
  payment_method: PaymentMethod;
  payment_reached_paid: boolean;
  payment_due: boolean;
  amount_due: PriceRead | null;
  subtotal: PriceRead;
  tax: PriceRead;
  total: PriceRead;
  delivery_address: AdminDeliveryAddressReadDTO | null;
  contact_phone: string | null;
  delivery_fee_note: string | null;
  customer_note: string | null;
  // Internal; never shown to the customer.
  admin_note: string | null;
  estimated_dispatch_at: string | null;
  placed_at: string;
  completed_at: string | null;
  cancelled_at: string | null;
  lines: AdminOrderLineReadDTO[];
  // Newest first.
  payments: AdminOrderPaymentReadDTO[];
  // Oldest first.
  status_history: AdminHistoryReadDTO[];
  refunds?: AdminOrderRefundReadDTO[];
  chargebacks?: AdminOrderChargebackReadDTO[];
  refund_balance?: AdminRefundBalanceReadDTO | null;
}

// POST /api/v1/admin/orders/{id}/items/{item}/transition (extra="forbid").
export interface OrderItemTransitionRequestDTO {
  target_status: OrderItemStatus;
  // A note kept in the status history, <= 500.
  reason?: string;
  // Required for -> cancelled from ready_to_ship, returned,
  // ready_for_pickup or shipped (the action's own cancel_reasons).
  cancel_reason?: CancelReason;
}

// POST /api/v1/admin/orders/{id}/cash-handover (extra="forbid"). The
// administrator types the cash received; the server never derives it and
// refuses anything but the exact live total (422 CASH_AMOUNT_MISMATCH).
export interface CashHandoverRequestDTO {
  amount_cents: number;
  currency: "USD";
  note?: string;
}

// PATCH /api/v1/admin/orders/{id} (extra="forbid"): blank or null clears.
export interface AdminOrderUpdateDTO {
  admin_note: string | null;
}

// POST /api/v1/admin/orders/{id}/cancel (extra="forbid").
export interface AdminOrderCancelRequestDTO {
  // 1-500, required.
  reason: string;
  cancel_reason?: CancelReason;
}

export interface StlDeliveryReadDTO {
  item_id: string;
  order_id: string;
  order_number: string;
  product_id: string;
  product_name: string;
  customer_id: string;
  customer_email: string;
  line_total_cents: number;
  currency: string;
  queued_at: string;
}

// Oldest first; keyset cursor.
export interface StlDeliveryPageDTO {
  items: StlDeliveryReadDTO[];
  next_cursor: string | null;
}

export interface StlDeliveriesQueryParams {
  cursor?: string;
  limit?: number;
}
