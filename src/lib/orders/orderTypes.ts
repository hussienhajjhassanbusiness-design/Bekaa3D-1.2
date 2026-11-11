import type { PriceRead, ProductType } from "@/lib/catalog/productTypes";

// #ARCHITECTURE-CUSTOMER-ORDER-WIRE-CONTRACT (FVS-029, phase 5E)
//
// Raw wire shapes for GET /api/v1/me/orders and GET /api/v1/me/orders/{id},
// transcribed field for field from the running backend 2dfb27b
// (`GET /openapi.json` components.schemas OrderPage, OrderSummaryRead,
// OrderDetailRead, OrderLineRead, OrderPaymentRead, StatusHistoryRead,
// OrderRefundRead, DeliveryAddressRead; canonically identical to
// docs/backend-handoff/openapi.json) and the implementation
// (src/app/ordering/api/orders.py, order_schemas.py, docs/order-history.md).
// snake_case on purpose: only orderModel.ts reads these.
//
// Access: a session is enough (no verified email). Anonymous -> 401
// AUTH_REQUIRED. Another customer's order and an unknown id give the SAME
// 404 NOT_FOUND; a malformed (non-UUID) id is a 422.
//
// The enums below are the backend's own, and the single frontend copy of
// them: checkoutTypes.ts re-exports these rather than declaring its own.
// A value the frontend does not know yet must still render (orderStatus.ts
// degrades every unknown value to a neutral label), so adapters never trust
// these unions at runtime.

export type OrderStatus =
  "pending_payment" | "cancelled" | "refunded" | "partially_refunded" | "completed" | "in_progress";

// `in_production` is in the enum but never returned to a customer: a line
// being printed reads `pending` (docs/order-history.md).
export type OrderItemStatus =
  | "pending"
  | "awaiting_delivery"
  | "in_production"
  | "ready_to_ship"
  | "shipped"
  | "delivered"
  | "returned"
  | "ready_for_pickup"
  | "picked_up"
  | "cancelled"
  | "refunded";

export type OrderSource = "cart" | "offer";
export type PaymentMethod = "online" | "cash";
export type FulfillmentMethod = "delivery" | "pickup";

// `OrderPaymentRead.status` is a plain string in the contract. The backend's
// PaymentStatus values (payments/domain/enums.py) are listed here for the
// label table only; any other string still renders.
export type KnownPaymentStatus =
  "pending" | "processing" | "paid" | "partially_refunded" | "refunded" | "failed" | "expired";

export interface OrderSummaryReadDTO {
  id: string;
  order_number: string;
  status: OrderStatus;
  payment_method: PaymentMethod;
  // Null for an STL-only order.
  fulfillment_method: FulfillmentMethod | null;
  // An unpaid cash order: pay the courier or at pickup.
  payment_due: boolean;
  // While payment_due: the live total of the lines not cancelled.
  amount_due: PriceRead | null;
  total: PriceRead;
  placed_at: string;
}

// Newest `placed_at` first. Cursor is opaque; null means no further page.
// `limit` 1-100, default 20. There is no total count.
export interface OrderPageDTO {
  items: OrderSummaryReadDTO[];
  next_cursor: string | null;
}

// Every field nullable in the contract (a snapshot taken at checkout).
export interface DeliveryAddressReadDTO {
  recipient_name: string | null;
  governorate: string | null;
  city: string | null;
  area: string | null;
  street: string | null;
  landmark_notes: string | null;
}

export interface OrderLineReadDTO {
  id: string;
  product_id: string;
  product_type: ProductType;
  // The name at purchase; later catalogue edits never change it.
  name: string;
  image_url: string | null;
  unit_price: PriceRead;
  quantity: number;
  line_total: PriceRead;
  fulfillment_status: OrderItemStatus;
  // STL: when the administrator emailed the file (ADR-019 manual delivery).
  fulfilled_at: string | null;
  cancelled_at: string | null;
  // Physical only: the first "I got it" / first problem report (VS-029b).
  receipt_confirmed_at: string | null;
  problem_reported_at: string | null;
}

// The live or paid attempt, else the most recent one. No provider reference.
export interface OrderPaymentReadDTO {
  status: string;
  provider: string;
  amount: PriceRead;
}

export interface StatusHistoryReadDTO {
  // Null for the order's own status.
  order_item_id: string | null;
  from_status: string | null;
  to_status: string;
  at: string;
}

export interface OrderRefundReadDTO {
  kind: "admin" | "cancellation" | "late_capture";
  status: "processing" | "refunded";
  amount: PriceRead;
  created_at: string;
}

export interface OrderDetailReadDTO {
  id: string;
  order_number: string;
  source: OrderSource;
  status: OrderStatus;
  fulfillment_method: FulfillmentMethod | null;
  payment_method: PaymentMethod;
  payment_due: boolean;
  amount_due: PriceRead | null;
  // Advisory capability flags. Their actions (cancel: FVS-031, retry:
  // FVS-027) are NOT mounted in this phase; the adapter does not expose them.
  can_cancel: boolean;
  can_retry_payment: boolean;
  // An unpaid online order: when it may be released if still unpaid.
  hold_expires_at: string | null;
  subtotal: PriceRead;
  tax: PriceRead;
  total: PriceRead;
  delivery_address: DeliveryAddressReadDTO | null;
  // Set for physical orders.
  contact_phone: string | null;
  // Set for delivery orders only. A fixed server sentence; the UI shows its
  // own ADR-024 courier-fee copy (as checkout does), keyed on presence.
  delivery_fee_note: string | null;
  // The estimated ready date.
  estimated_dispatch_at: string | null;
  placed_at: string;
  completed_at: string | null;
  cancelled_at: string | null;
  customer_note: string | null;
  lines: OrderLineReadDTO[];
  // Null while a cash order is unpaid.
  payment: OrderPaymentReadDTO | null;
  // Oldest first.
  status_history: StatusHistoryReadDTO[];
  // Oldest first. Not in `required` in the schema: may be absent.
  refunds?: OrderRefundReadDTO[];
}

// #FVS027-PAYMENT-RETRY-WIRE-CONTRACT (phase 5F)
//
// POST /api/v1/me/orders/{order_id}/payments (backend 2dfb27b
// ordering/api/payment_retry.py; docs/payment-recovery.md; running
// /openapi.json PaymentRetryRequest / PaymentRetryRead). Verified session,
// CSRF, required `Idempotency-Key` (^[A-Za-z0-9._:-]{8,255}$, scope
// `payment_retry:{order_id}` per user, kept 24 h).
//
// Body `extra="forbid"`: only `payment_provider?` (1-32). The frontend
// sends `{}` — the server reuses the previous attempt's provider while it
// is configured, and the frontend never names a provider. The amount is
// always the order's own total and cannot be sent.
export type PaymentRetryRequestDTO = Record<string, never>;

export interface RetryOrderReadDTO {
  id: string;
  order_number: string;
  status: OrderStatus;
  total_cents: number;
  currency: string;
  // The new hold deadline: a retry restarts the hold.
  hold_expires_at: string;
}

export interface RetryPaymentReadDTO {
  id: string;
  // A plain string on the wire (backend PaymentStatus); `pending` on a 201.
  status: string;
  provider: string;
  amount_cents: number;
  currency: string;
  // The provider's payment page; null if none. Opaque: followed exactly as
  // given (after the absolute-http(s) check), never parsed.
  redirect_url: string | null;
}

export interface PaymentRetryReadDTO {
  order: RetryOrderReadDTO;
  payment: RetryPaymentReadDTO;
}
