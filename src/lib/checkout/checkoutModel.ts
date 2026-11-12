import type { ProductType, PriceRead } from "@/lib/catalog/productTypes";
import { governorateLabel } from "@/lib/addresses/addressModel";
import { isPaymentProviderAllowed } from "./paymentProviderGuard";
import type {
  CheckoutAddressReadDTO,
  CheckoutLineReadDTO,
  CheckoutReadDTO,
  FulfillmentMethod,
  OrderItemStatus,
  OrderStatus,
  PaymentMethod,
} from "./checkoutTypes";

// #ARCHITECTURE-CHECKOUT-RESPONSE-ADAPTER
//
// The one conversion of a 201 CheckoutRead into what the page shows. Every
// amount here is the server's (live prices, server totals); nothing is
// summed or derived on the client. `next` only picks which response-backed
// screen to show; it never claims a payment outcome. An online order is
// `pending_payment` with a `pending` payment: paid is decided later by the
// backend after it verifies the provider (FVS-027), never here.

export interface Money {
  amountCents: number;
  currency: string;
}

export interface CheckoutResultLine {
  id: string;
  productId: string;
  productType: ProductType;
  name: string;
  unitPrice: Money;
  quantity: number;
  lineTotal: Money;
  fulfillmentStatus: OrderItemStatus;
}

export interface CheckoutResultPayment {
  id: string;
  status: string;
  provider: string;
  redirectUrl: string | null;
}

export type CheckoutNextStep = "cash-confirmation" | "online-redirect" | "online-no-redirect";

export interface CheckoutResultModel {
  orderId: string;
  orderNumber: string;
  status: OrderStatus;
  paymentMethod: PaymentMethod;
  fulfillmentMethod: FulfillmentMethod | null;
  subtotal: Money;
  tax: Money;
  total: Money;
  placedAt: string;
  estimatedDispatchAt: string | null;
  deliveryAddress: { recipientName: string; lines: string[] } | null;
  paymentDue: boolean;
  amountDue: Money | null;
  lines: CheckoutResultLine[];
  payment: CheckoutResultPayment | null;
  // STLs already owned when the order was placed: NOT charged, NOT in lines.
  droppedProductIds: string[];
  next: CheckoutNextStep;
}

// The redirect is opaque: it is followed exactly as given, its parameters
// are never read. The only check is that it is an absolute http(s) URL, so
// a malformed value can never become a `javascript:`/`data:` navigation.
export function isFollowableRedirect(url: string | null): url is string {
  if (!url) {
    return false;
  }
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:";
  } catch {
    return false;
  }
}

function money(price: PriceRead): Money {
  return { amountCents: price.amount_cents, currency: price.currency };
}

function adaptLine(dto: CheckoutLineReadDTO): CheckoutResultLine {
  return {
    id: dto.id,
    productId: dto.product_id,
    productType: dto.product_type,
    name: dto.name,
    unitPrice: money(dto.unit_price),
    quantity: dto.quantity,
    lineTotal: money(dto.line_total),
    fulfillmentStatus: dto.fulfillment_status,
  };
}

function adaptAddress(dto: CheckoutAddressReadDTO): {
  recipientName: string;
  lines: string[];
} {
  const street = [dto.street, dto.area].filter((part): part is string => Boolean(part)).join(", ");
  const lines = [street, `${dto.city}, ${governorateLabel(dto.governorate)}`, dto.landmark_notes ?? ""].filter(
    (line) => line !== ""
  );
  return { recipientName: dto.recipient_name, lines };
}

export function adaptCheckoutRead(dto: CheckoutReadDTO): CheckoutResultModel {
  const order = dto.order;
  const payment: CheckoutResultPayment | null = dto.payment
    ? {
        id: dto.payment.id,
        status: dto.payment.status,
        provider: dto.payment.provider,
        redirectUrl: dto.payment.redirect_url,
      }
    : null;

  let next: CheckoutNextStep;
  if (payment === null) {
    next = "cash-confirmation";
  } else {
    // Phase 6F: a production build never follows the mock provider's page
    // (paymentProviderGuard.ts); that shows the "no payment page" result.
    next = isFollowableRedirect(payment.redirectUrl) && isPaymentProviderAllowed(payment.provider) ? "online-redirect" : "online-no-redirect";
  }

  return {
    orderId: order.id,
    orderNumber: order.order_number,
    status: order.status,
    paymentMethod: order.payment_method,
    fulfillmentMethod: order.fulfillment_method,
    subtotal: money(order.subtotal),
    tax: money(order.tax),
    total: money(order.total),
    placedAt: order.placed_at,
    estimatedDispatchAt: order.estimated_dispatch_at,
    deliveryAddress: order.delivery_address ? adaptAddress(order.delivery_address) : null,
    paymentDue: order.payment_due,
    amountDue: order.amount_due ? money(order.amount_due) : null,
    lines: order.lines.map(adaptLine),
    payment,
    droppedProductIds: dto.dropped_lines.map((line) => line.product_id),
    next,
  };
}
