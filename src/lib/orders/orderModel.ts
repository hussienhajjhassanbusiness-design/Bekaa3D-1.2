import type { PriceRead, ProductType } from "@/lib/catalog/productTypes";
import { governorateLabel } from "@/lib/addresses/addressModel";
import type {
  DeliveryAddressReadDTO,
  FulfillmentMethod,
  OrderDetailReadDTO,
  OrderItemStatus,
  OrderLineReadDTO,
  OrderSource,
  OrderStatus,
  OrderSummaryReadDTO,
  PaymentMethod,
} from "./orderTypes";

// #ARCHITECTURE-CUSTOMER-ORDER-ADAPTER (FVS-029, phase 5E)
//
// The one conversion of the real /me/orders responses into what the
// account pages show. Every amount, status and date is the server's,
// passed through unchanged: nothing is summed, derived or inferred
// (no shipping charge, no "paid" from a redirect, no download).
//
// #SECURITY-CUSTOMER-ORDER-PROJECTION — the backend never returns admin
// notes, provider references, the checkout email or the phone hash on
// these routes, and no model here has a field for one.
//
// `can_cancel` / `can_retry_payment` are deliberately NOT carried: their
// actions belong to FVS-031 / FVS-027 and are not mounted in phase 5E.

export interface Money {
  amountCents: number;
  currency: string;
}

export interface OrderSummaryModel {
  id: string;
  orderNumber: string;
  status: OrderStatus;
  paymentMethod: PaymentMethod;
  fulfillmentMethod: FulfillmentMethod | null;
  paymentDue: boolean;
  amountDue: Money | null;
  total: Money;
  placedAt: string;
}

export interface OrderLineModel {
  id: string;
  productId: string;
  productType: ProductType;
  name: string;
  imageUrl: string | null;
  unitPrice: Money;
  quantity: number;
  lineTotal: Money;
  fulfillmentStatus: OrderItemStatus;
  fulfilledAt: string | null;
  cancelledAt: string | null;
  receiptConfirmedAt: string | null;
  problemReportedAt: string | null;
}

export interface OrderPaymentModel {
  // A plain string in the contract; orderStatus.ts labels it safely.
  status: string;
  provider: string;
  amount: Money;
}

export interface OrderHistoryEntryModel {
  // Null for the order's own status.
  lineName: string | null;
  lineProductType: ProductType | null;
  toStatus: string;
  at: string;
}

export interface OrderRefundModel {
  kind: string;
  status: string;
  amount: Money;
  createdAt: string;
}

export interface OrderDeliveryAddressModel {
  recipientName: string | null;
  lines: string[];
}

export interface OrderDetailModel {
  id: string;
  orderNumber: string;
  source: OrderSource;
  status: OrderStatus;
  paymentMethod: PaymentMethod;
  fulfillmentMethod: FulfillmentMethod | null;
  paymentDue: boolean;
  amountDue: Money | null;
  holdExpiresAt: string | null;
  subtotal: Money;
  tax: Money;
  total: Money;
  deliveryAddress: OrderDeliveryAddressModel | null;
  contactPhone: string | null;
  hasDeliveryFeeNote: boolean;
  estimatedDispatchAt: string | null;
  placedAt: string;
  completedAt: string | null;
  cancelledAt: string | null;
  customerNote: string | null;
  lines: OrderLineModel[];
  payment: OrderPaymentModel | null;
  history: OrderHistoryEntryModel[];
  refunds: OrderRefundModel[];
  containsPhysical: boolean;
  containsStl: boolean;
}

// A line id in status_history that is not among `lines` (should not
// happen) is still shown, under a neutral name.
const UNKNOWN_LINE_NAME = "An item";

function money(price: PriceRead): Money {
  return { amountCents: price.amount_cents, currency: price.currency };
}

function present(value: string | null | undefined): value is string {
  return typeof value === "string" && value.trim() !== "";
}

function adaptAddress(dto: DeliveryAddressReadDTO): OrderDeliveryAddressModel {
  const street = [dto.street, dto.area].filter(present).join(", ");
  const place = [dto.city, present(dto.governorate) ? governorateLabel(dto.governorate) : null]
    .filter(present)
    .join(", ");
  const lines = [street, place, dto.landmark_notes].filter(present);
  return { recipientName: present(dto.recipient_name) ? dto.recipient_name : null, lines };
}

function adaptLine(dto: OrderLineReadDTO): OrderLineModel {
  return {
    id: dto.id,
    productId: dto.product_id,
    productType: dto.product_type,
    name: dto.name,
    imageUrl: dto.image_url,
    unitPrice: money(dto.unit_price),
    quantity: dto.quantity,
    lineTotal: money(dto.line_total),
    fulfillmentStatus: dto.fulfillment_status,
    fulfilledAt: dto.fulfilled_at,
    cancelledAt: dto.cancelled_at,
    receiptConfirmedAt: dto.receipt_confirmed_at,
    problemReportedAt: dto.problem_reported_at,
  };
}

export function adaptOrderSummary(dto: OrderSummaryReadDTO): OrderSummaryModel {
  return {
    id: dto.id,
    orderNumber: dto.order_number,
    status: dto.status,
    paymentMethod: dto.payment_method,
    fulfillmentMethod: dto.fulfillment_method,
    paymentDue: dto.payment_due,
    amountDue: dto.amount_due ? money(dto.amount_due) : null,
    total: money(dto.total),
    placedAt: dto.placed_at,
  };
}

export function adaptOrderDetail(dto: OrderDetailReadDTO): OrderDetailModel {
  const lines = dto.lines.map(adaptLine);
  const byId = new Map(lines.map((line) => [line.id, line]));

  return {
    id: dto.id,
    orderNumber: dto.order_number,
    source: dto.source,
    status: dto.status,
    paymentMethod: dto.payment_method,
    fulfillmentMethod: dto.fulfillment_method,
    paymentDue: dto.payment_due,
    amountDue: dto.amount_due ? money(dto.amount_due) : null,
    holdExpiresAt: dto.hold_expires_at,
    subtotal: money(dto.subtotal),
    tax: money(dto.tax),
    total: money(dto.total),
    deliveryAddress: dto.delivery_address ? adaptAddress(dto.delivery_address) : null,
    contactPhone: present(dto.contact_phone) ? dto.contact_phone : null,
    hasDeliveryFeeNote: present(dto.delivery_fee_note),
    estimatedDispatchAt: dto.estimated_dispatch_at,
    placedAt: dto.placed_at,
    completedAt: dto.completed_at,
    cancelledAt: dto.cancelled_at,
    customerNote: present(dto.customer_note) ? dto.customer_note : null,
    lines,
    payment: dto.payment
      ? { status: dto.payment.status, provider: dto.payment.provider, amount: money(dto.payment.amount) }
      : null,
    history: dto.status_history.map((entry) => {
      if (entry.order_item_id === null) {
        return { lineName: null, lineProductType: null, toStatus: entry.to_status, at: entry.at };
      }
      const line = byId.get(entry.order_item_id);
      return {
        lineName: line?.name ?? UNKNOWN_LINE_NAME,
        lineProductType: line?.productType ?? "physical",
        toStatus: entry.to_status,
        at: entry.at,
      };
    }),
    refunds: (dto.refunds ?? []).map((refund) => ({
      kind: refund.kind,
      status: refund.status,
      amount: money(refund.amount),
      createdAt: refund.created_at,
    })),
    containsPhysical: lines.some((line) => line.productType === "physical"),
    containsStl: lines.some((line) => line.productType === "stl"),
  };
}

// The backend types `order_id` as a UUID and answers anything else with a
// 422. The route treats a non-UUID exactly like an unknown order (not
// found) without calling the API.
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isOrderId(value: string): boolean {
  return UUID_PATTERN.test(value);
}
