import type { PriceRead, ProductType } from "@/lib/catalog/productTypes";

// #ARCHITECTURE-CHECKOUT-WIRE-CONTRACT
//
// Raw wire shapes for POST /api/v1/checkout, transcribed field for field
// from the running backend 2dfb27b (`GET /openapi.json` components.schemas
// CheckoutRequest, AcceptedPriceIn, CheckoutRead, CheckoutOrderRead,
// CheckoutLineRead, CheckoutAddressRead, CheckoutPaymentRead,
// DroppedLineRead, PaymentMethod, FulfillmentMethod, OrderStatus,
// OrderItemStatus, OrderSource; identical to docs/backend-handoff/
// openapi.json) and the implementation (src/app/ordering/api/
// checkout_schemas.py, domain/fulfillment.py, docs/checkout.md).
// snake_case on purpose: only checkoutPayload.ts / checkoutModel.ts touch
// these.
//
// Headers: `Idempotency-Key` (required, ^[A-Za-z0-9._:-]{8,255}$) and the
// double-submit `X-CSRF-Token`. Auth: a verified customer session
// (403 EMAIL_VERIFICATION_REQUIRED otherwise).

import type {
  FulfillmentMethod,
  OrderItemStatus,
  OrderSource,
  OrderStatus,
  PaymentMethod,
} from "@/lib/orders/orderTypes";

// The order enums are owned by the customer-order domain (FVS-029).
export type { FulfillmentMethod, OrderItemStatus, OrderSource, OrderStatus, PaymentMethod };

// `extra="forbid"`: no amount, total or price is ever sent; the server
// charges live prices. Fulfillment matrix (domain/fulfillment.py, run on
// the lines kept after already-owned STLs are dropped):
//   STL only          -> fulfillment_method, address_id, contact_phone absent
//   physical delivery -> fulfillment_method "delivery", address_id required,
//                        contact_phone ABSENT (the address's phone is used)
//   physical pickup   -> fulfillment_method "pickup", contact_phone required,
//                        address_id ABSENT
// Cash needs every kept line physical. `payment_provider` is omitted: the
// server uses its one configured provider (currently only the mock).
export interface CheckoutRequestDTO {
  payment_method: PaymentMethod;
  payment_provider?: string;
  fulfillment_method?: FulfillmentMethod;
  address_id?: string;
  // <= 32 chars, a Lebanese number; the server normalises it to E.164.
  contact_phone?: string;
  // <= 1000 chars.
  customer_note?: string;
  accept_terms: true;
  // Required (true) while an STL line remains.
  accept_digital_final_sale?: true;
  // Required (true) for cash; ignored for online, so never sent with it.
  accept_cash_terms?: true;
  // <= 50. Each entry confirms the LIVE price of one product exactly.
  accepted_price_changes?: AcceptedPriceDTO[];
}

export interface AcceptedPriceDTO {
  product_id: string;
  amount_cents: number;
  currency: string;
}

export interface CheckoutLineReadDTO {
  id: string;
  product_id: string;
  product_type: ProductType;
  name: string;
  unit_price: PriceRead;
  quantity: number;
  line_total: PriceRead;
  fulfillment_status: OrderItemStatus;
}

// The delivery snapshot: never the contact phone or its hash.
export interface CheckoutAddressReadDTO {
  recipient_name: string;
  governorate: string;
  city: string;
  area: string | null;
  street: string | null;
  landmark_notes: string | null;
}

export interface CheckoutOrderReadDTO {
  id: string;
  order_number: string;
  source: OrderSource;
  status: OrderStatus;
  payment_method: PaymentMethod;
  // Null for a digital-only order.
  fulfillment_method: FulfillmentMethod | null;
  subtotal: PriceRead;
  tax: PriceRead;
  total: PriceRead;
  placed_at: string;
  estimated_dispatch_at: string | null;
  // Delivery only (server text); the UI uses its own ADR-024 copy instead.
  delivery_fee_note: string | null;
  delivery_address: CheckoutAddressReadDTO | null;
  // True only for an unpaid cash order: pay the courier or at pickup.
  payment_due: boolean;
  // Cash orders only: the live total.
  amount_due: PriceRead | null;
  lines: CheckoutLineReadDTO[];
}

export interface CheckoutPaymentReadDTO {
  id: string;
  // A plain string in the contract ("pending" at checkout).
  status: string;
  provider: string;
  // The provider's payment page; null if none. Opaque.
  redirect_url: string | null;
}

// STLs bought since they were added: not charged and not in `order.lines`.
export interface DroppedLineReadDTO {
  product_id: string;
  reason: "already_owned";
}

export interface CheckoutReadDTO {
  order: CheckoutOrderReadDTO;
  // Null for a cash order.
  payment: CheckoutPaymentReadDTO | null;
  dropped_lines: DroppedLineReadDTO[];
}
