import type { AdminOrderDetailDTO, AdminOrderLineReadDTO, AdminOrderSummaryReadDTO, StlDeliveryReadDTO } from "./adminOrderTypes";

// Test-only builders for the real admin order wire shapes (backend 2dfb27b).
export const ADMIN_ORDER_ID = "3c1a7e2b-5f2d-4c1e-9a4b-1d2e3f4a5b6c";
export const ADMIN_LINE_ID = "4d2b8f3c-6a3e-4d2f-8b5c-2e3f4a5b6c7d";

const usd = (amount_cents: number) => ({ amount_cents, currency: "USD" });

export function adminLineDTO(overrides: Partial<AdminOrderLineReadDTO> = {}): AdminOrderLineReadDTO {
  return {
    id: ADMIN_LINE_ID,
    product_id: "p-1",
    product_type: "physical",
    name: "Articulated Dragon",
    image_url: null,
    unit_price: usd(1800),
    quantity: 2,
    line_total: usd(3600),
    fulfillment_status: "pending",
    fulfilled_at: null,
    delivered_by: null,
    cancelled_at: null,
    cancel_reason: null,
    offer_id: null,
    lead_time_days: 3,
    batch_size: null,
    receipt_confirmed_at: null,
    problem_reported_at: null,
    available_actions: [
      { target_status: "in_production", cancel_reasons: [] },
      { target_status: "cancelled", cancel_reasons: [] },
    ],
    ...overrides,
  };
}

export function adminDetailDTO(overrides: Partial<AdminOrderDetailDTO> = {}): AdminOrderDetailDTO {
  return {
    id: ADMIN_ORDER_ID,
    order_number: "B3D-ADMIN001",
    source: "cart",
    customer_id: "c-1",
    customer_email: "rana@example.com",
    status: "in_progress",
    fulfillment_method: "delivery",
    payment_method: "cash",
    payment_reached_paid: false,
    payment_due: true,
    amount_due: usd(3600),
    subtotal: usd(3600),
    tax: usd(0),
    total: usd(3600),
    delivery_address: {
      recipient_name: "Rana Haddad",
      governorate: "beqaa",
      city: "Zahle",
      area: null,
      street: "Main St 12",
      landmark_notes: "Blue gate",
    },
    contact_phone: "+96170123456",
    delivery_fee_note: "The courier collects the delivery fee.",
    customer_note: "Call first",
    admin_note: null,
    estimated_dispatch_at: "2026-11-14T00:00:00Z",
    placed_at: "2026-11-10T09:30:00Z",
    completed_at: null,
    cancelled_at: null,
    lines: [adminLineDTO()],
    payments: [],
    status_history: [
      { order_item_id: null, from_status: null, to_status: "in_progress", actor_user_id: "c-1", reason: null, at: "2026-11-10T09:30:00Z" },
    ],
    refunds: [],
    chargebacks: [],
    refund_balance: null,
    ...overrides,
  };
}

export function adminSummaryDTO(overrides: Partial<AdminOrderSummaryReadDTO> = {}): AdminOrderSummaryReadDTO {
  return {
    id: ADMIN_ORDER_ID,
    order_number: "B3D-ADMIN001",
    customer_id: "c-1",
    customer_email: "rana@example.com",
    status: "in_progress",
    fulfillment_method: "delivery",
    payment_method: "cash",
    payment_due: true,
    amount_due: usd(3600),
    total: usd(3600),
    estimated_dispatch_at: null,
    placed_at: "2026-11-10T09:30:00Z",
    ...overrides,
  };
}

export function stlDeliveryDTO(overrides: Partial<StlDeliveryReadDTO> = {}): StlDeliveryReadDTO {
  return {
    item_id: "5e3c9a4d-7b4f-4e3a-9c6d-3f4a5b6c7d8e",
    order_id: ADMIN_ORDER_ID,
    order_number: "B3D-ADMIN002",
    product_id: "p-stl",
    product_name: "Dragon STL",
    customer_id: "c-2",
    customer_email: "sami@example.com",
    line_total_cents: 900,
    currency: "USD",
    queued_at: "2026-11-10T10:00:00Z",
    ...overrides,
  };
}
