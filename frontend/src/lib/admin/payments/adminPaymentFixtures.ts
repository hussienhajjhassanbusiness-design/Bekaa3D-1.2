import type { AdminPaymentDetailDTO, AdminPaymentReadDTO, RefundDetailDTO } from "./adminPaymentTypes";

// Test-only builders for the real admin payment/refund wire shapes (backend 2dfb27b).
const ID = "11111111-1111-4111-8111-111111111111";

export function refundDTO(overrides: Partial<RefundDetailDTO> = {}): RefundDetailDTO {
  return {
    id: "r-1", order_id: ID, order_number: "B3D-R1", customer_id: "c-1", payment_id: "p-1", payment_provider: "mock",
    kind: "admin", status: "pending", owed: false, amount_cents: 1800, currency: "USD", reason: "Damaged",
    requested_by: "a-1", approved_by: "a-1", items: [{ order_item_id: "l-1", product_name: "Dragon", amount_cents: 1800 }],
    reissue_of_refund_id: null, reissued_by_refund_id: null, reissued_at: null, settled_at: null, settled_by: null,
    settlement_reference: null, settlement_note: null, failed_at: null, failed_by: null, failure_reason: null,
    voided_at: null, voided_by: null, void_reason: null, created_at: "2026-11-11T10:00:00Z", ...overrides,
  };
}

export const PAYMENT_ID = "66666666-6666-4666-8666-666666666666";

export function paymentDTO(overrides: Partial<AdminPaymentReadDTO> = {}): AdminPaymentReadDTO {
  return {
    id: PAYMENT_ID, order_id: ID, order_number: "B3D-R1", provider: "mock", status: "paid", amount_cents: 3600,
    currency: "USD", captured_amount_cents: null, captured_currency: null, provider_payment_id: "mock_abc",
    initiated_at: "2026-11-10T10:00:00Z", verified_at: "2026-11-10T10:01:00Z", failed_at: null, expired_at: null,
    late_captured_at: null, needs_manual_confirmation: false, unprocessed_event_count: 0, ...overrides,
  };
}

export function paymentDetailDTO(overrides: Partial<AdminPaymentDetailDTO> = {}): AdminPaymentDetailDTO {
  return {
    payment: paymentDTO(),
    order: { id: ID, order_number: "B3D-R1", status: "in_progress", total_cents: 3600, currency: "USD", placed_at: "2026-11-10T10:00:00Z", cancelled_at: null, hold_expires_at: null, manual_release_available_at: null },
    events: [{ id: "e-1", event_type: "payment.paid", signature_valid: true, received_at: "2026-11-10T10:01:00Z", processed_at: "2026-11-10T10:01:01Z", processing_error: null }],
    history: [{ action: "payment.verified", actor_user_id: null, created_at: "2026-11-10T10:01:01Z", data: { secret: "RAW DATA" } }],
    available_actions: ["reconcile"],
    ...overrides,
  };
}
