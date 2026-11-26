import type {
  OrderDetailReadDTO,
  OrderLineReadDTO,
  OrderPageDTO,
  OrderSummaryReadDTO,
} from "./orderTypes";

// Test-only builders for the real /me/orders wire shapes (backend 2dfb27b).
// Shared by the unit tests; e2e/support has its own copy so Playwright
// stays self-contained.

export const ORDER_ID = "0b6f2a52-7f5d-4f3e-9c55-3b8b1f5d2a10";

export function summaryDTO(overrides: Partial<OrderSummaryReadDTO> = {}): OrderSummaryReadDTO {
  return {
    id: ORDER_ID,
    order_number: "B3D-2026-000123",
    status: "in_progress",
    payment_method: "cash",
    fulfillment_method: "delivery",
    payment_due: true,
    amount_due: { amount_cents: 2500, currency: "USD" },
    total: { amount_cents: 2500, currency: "USD" },
    placed_at: "2026-11-10T09:30:00Z",
    ...overrides,
  };
}

export function pageDTO(items: OrderSummaryReadDTO[], nextCursor: string | null = null): OrderPageDTO {
  return { items, next_cursor: nextCursor };
}

export function lineDTO(overrides: Partial<OrderLineReadDTO> = {}): OrderLineReadDTO {
  return {
    id: "line-physical-1",
    product_id: "prod-1",
    product_type: "physical",
    name: "Cedar Planter",
    image_url: "https://media.example/planter.jpg",
    unit_price: { amount_cents: 1250, currency: "USD" },
    quantity: 2,
    line_total: { amount_cents: 2500, currency: "USD" },
    fulfillment_status: "pending",
    fulfilled_at: null,
    cancelled_at: null,
    receipt_confirmed_at: null,
    problem_reported_at: null,
    ...overrides,
  };
}

export function stlLineDTO(overrides: Partial<OrderLineReadDTO> = {}): OrderLineReadDTO {
  return lineDTO({
    id: "line-stl-1",
    product_id: "prod-stl-1",
    product_type: "stl",
    name: "Dragon STL",
    image_url: null,
    unit_price: { amount_cents: 500, currency: "USD" },
    quantity: 1,
    line_total: { amount_cents: 500, currency: "USD" },
    fulfillment_status: "awaiting_delivery",
    ...overrides,
  });
}

export function detailDTO(overrides: Partial<OrderDetailReadDTO> = {}): OrderDetailReadDTO {
  return {
    id: ORDER_ID,
    order_number: "B3D-2026-000123",
    source: "cart",
    status: "in_progress",
    fulfillment_method: "delivery",
    payment_method: "cash",
    payment_due: true,
    amount_due: { amount_cents: 2500, currency: "USD" },
    can_cancel: true,
    can_retry_payment: false,
    hold_expires_at: null,
    subtotal: { amount_cents: 2500, currency: "USD" },
    tax: { amount_cents: 0, currency: "USD" },
    total: { amount_cents: 2500, currency: "USD" },
    delivery_address: {
      recipient_name: "Rana Haddad",
      governorate: "bekaa",
      city: "Zahle",
      area: "Hoch el Oumara",
      street: "Main Street 12",
      landmark_notes: "Blue gate",
    },
    contact_phone: "+96170123456",
    delivery_fee_note: "The courier collects the delivery fee.",
    estimated_dispatch_at: "2026-11-14T00:00:00Z",
    placed_at: "2026-11-10T09:30:00Z",
    completed_at: null,
    cancelled_at: null,
    customer_note: "Please call before delivery",
    lines: [lineDTO()],
    payment: null,
    status_history: [{ order_item_id: null, from_status: null, to_status: "in_progress", at: "2026-11-10T09:30:00Z" }],
    refunds: [],
    ...overrides,
  };
}

// A pending online (mock) order: unpaid, payment row pending.
export function pendingOnlineDetailDTO(overrides: Partial<OrderDetailReadDTO> = {}): OrderDetailReadDTO {
  return detailDTO({
    status: "pending_payment",
    payment_method: "online",
    payment_due: false,
    amount_due: null,
    can_cancel: false,
    can_retry_payment: false,
    hold_expires_at: "2026-11-10T10:00:00Z",
    payment: { status: "pending", provider: "mock", amount: { amount_cents: 2500, currency: "USD" } },
    status_history: [
      { order_item_id: null, from_status: null, to_status: "pending_payment", at: "2026-11-10T09:30:00Z" },
    ],
    ...overrides,
  });
}
