import type { OrderStatus } from "@/lib/orders/orderTypes";

// #FVS028-ADMIN-PAYMENT-WIRE-CONTRACT (phase 5I)
//
// Raw wire shapes for the administrator's payment and refund routes,
// transcribed from the running backend 2dfb27b (`/openapi.json`
// AdminPaymentPage, AdminPaymentRead, AdminPaymentDetail,
// AdminPaymentOrderRead, AdminPaymentEventRead, AdminPaymentHistoryRead,
// ReconcileQueued, ManualPaymentConfirmRequest, ManualConfirmRead,
// RefundCreate, RefundItemCreate, RefundDetail, RefundPage,
// RefundSettlementRequest, RefundFailureRequest, RefundVoidRequest) and
// payments/api/admin_payments.py, admin_refunds.py; payments/domain/
// enums.py, refunds.py, manual.py, limits.py.
//
// Admin with completed MFA; writes need X-CSRF-Token. No live provider
// exists (VS-032): online payments run on the `mock` provider. The admin
// pays a refund in the provider's dashboard and then records it here; this
// site never moves money (ADR-024 d16). No shipping amount exists to refund
// (ADR-024) and no STL entitlement exists to revoke (ADR-019).

// backend PaymentStatus / PaymentProvider / RefundStatus / RefundKind.
export type AdminPaymentStatus = "pending" | "processing" | "paid" | "partially_refunded" | "refunded" | "failed" | "expired";
export type PaymentProvider = "mock" | "cash";
export type RefundStatus = "pending" | "settled" | "failed" | "voided";
export type RefundKind = "admin" | "cancellation" | "late_capture";

export interface AdminPaymentReadDTO {
  id: string;
  order_id: string;
  order_number: string | null;
  provider: string;
  status: string;
  amount_cents: number;
  currency: string;
  captured_amount_cents: number | null;
  captured_currency: string | null;
  provider_payment_id: string | null;
  initiated_at: string;
  verified_at: string | null;
  failed_at: string | null;
  expired_at: string | null;
  late_captured_at: string | null;
  needs_manual_confirmation: boolean;
  unprocessed_event_count: number;
}

// Oldest first (late_captured=true: the late captures to refund).
export interface AdminPaymentPageDTO {
  items: AdminPaymentReadDTO[];
  next_cursor: string | null;
}

export interface AdminPaymentsQueryParams {
  status?: AdminPaymentStatus;
  provider?: PaymentProvider;
  order_id?: string;
  late_captured?: boolean;
  cursor?: string;
  limit?: number;
}

export interface AdminPaymentOrderReadDTO {
  id: string;
  order_number: string;
  status: OrderStatus;
  total_cents: number;
  currency: string;
  placed_at: string;
  cancelled_at: string | null;
  hold_expires_at: string | null;
  manual_release_available_at: string | null;
}

// Webhook events, without payloads. `processing_error` is backend text and
// is never rendered; only its presence is shown.
export interface AdminPaymentEventReadDTO {
  id: string;
  event_type: string | null;
  signature_valid: boolean | null;
  received_at: string;
  processed_at: string | null;
  processing_error: string | null;
}

// Audit entries for the payment. `data` is not rendered.
export interface AdminPaymentHistoryReadDTO {
  action: string;
  actor_user_id: string | null;
  created_at: string;
  data: Record<string, unknown> | null;
}

export type AdminPaymentAction = "reconcile" | "confirm" | "release_order";

export interface AdminPaymentDetailDTO {
  payment: AdminPaymentReadDTO;
  order: AdminPaymentOrderReadDTO;
  events: AdminPaymentEventReadDTO[];
  history: AdminPaymentHistoryReadDTO[];
  // Online, provider with a status API: reconcile; without one: confirm.
  // Cash: none. release_order only after the unpaid order's grace.
  available_actions: AdminPaymentAction[];
}

// POST /api/v1/admin/payments/{id}/reconcile -> 202.
export interface ReconcileQueuedDTO {
  payment: Pick<AdminPaymentReadDTO, "id" | "order_id" | "status" | "amount_cents" | "currency">;
  reconcile: "queued";
}

// POST /api/v1/admin/payments/{id}/confirm (extra="forbid").
export interface ManualPaymentConfirmRequestDTO {
  provider_reference: string; // 1-255
  verified_amount_cents: number; // >= 0
  verified_currency: string; // 3 letters, default USD
  reason: string; // 10-1000
}

export interface RefundItemCreateDTO {
  order_item_id: string;
  amount_cents: number; // > 0
}

// POST /api/v1/admin/orders/{order_id}/refunds (extra="forbid") with a
// required Idempotency-Key. 1-50 items, reason 1-1000.
export interface RefundCreateDTO {
  items: RefundItemCreateDTO[];
  reason: string;
}

export interface RefundDetailDTO {
  id: string;
  order_id: string;
  order_number: string;
  customer_id: string;
  payment_id: string;
  payment_provider: string;
  kind: string;
  status: string;
  // Failed and not reissued: still in the obligations queue.
  owed: boolean;
  amount_cents: number;
  currency: string;
  reason: string;
  requested_by: string | null;
  approved_by: string | null;
  items: { order_item_id: string; product_name: string; amount_cents: number }[];
  reissue_of_refund_id: string | null;
  reissued_by_refund_id: string | null;
  reissued_at: string | null;
  settled_at: string | null;
  settled_by: string | null;
  settlement_reference: string | null;
  settlement_note: string | null;
  failed_at: string | null;
  failed_by: string | null;
  failure_reason: string | null;
  voided_at: string | null;
  voided_by: string | null;
  void_reason: string | null;
  created_at: string;
}

export interface RefundPageDTO {
  items: RefundDetailDTO[];
  next_cursor: string | null;
}

// GET /api/v1/admin/refunds: queue=true (default) is the obligations queue
// (pending or owed, oldest first); queue=false is the history.
export interface AdminRefundsQueryParams {
  queue?: boolean;
  status?: RefundStatus;
  kind?: RefundKind;
  order_id?: string;
  cursor?: string;
  limit?: number;
}

export interface RefundSettlementRequestDTO {
  reference?: string; // <= 200
  note?: string; // <= 1000
}

export interface RefundReasonRequestDTO {
  reason: string; // 1-1000 (fail, void)
}
