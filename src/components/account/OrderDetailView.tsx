import Link from "next/link";
import type { ReactNode } from "react";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { FULFILLMENT_COPY } from "@/lib/checkout/checkoutCopy";
import type { PickupOption } from "@/lib/checkout/checkoutEligibility";
import type { Money, OrderDetailModel } from "@/lib/orders/orderModel";
import {
  describeHistoryStatus,
  describeOrderStatus,
  describeRefundKind,
  describeRefundStatus,
} from "@/lib/orders/orderStatus";
import { formatOrderDate, formatOrderDateTime } from "@/lib/orders/orderFormat";
import { OrderLineItem } from "./OrderLineItem";
import { OrderPaymentSection, type OrderPaymentControls } from "./OrderPaymentSection";
import { StatusTimeline } from "./StatusTimeline";

export interface OrderDetailViewProps {
  order: OrderDetailModel;
  // Current pickup location/hours from public settings. The order itself
  // carries no pickup snapshot, so this is labelled as current info.
  pickup?: PickupOption;
  // FVS-027: the page's bounded verification and retry controls. Absent,
  // the payment section is read-only.
  paymentControls?: OrderPaymentControls;
  // FVS-031: the page's "Order actions" section (OrderCustomerActions),
  // rendered under the items. Absent, the view stays read-only.
  customerActions?: ReactNode;
}

// #FVS029-ORDER-DETAIL
//
// Renders GET /me/orders/{id} truthfully and read-only:
//   - cash: `payment` is null while unpaid; the amount due (`amount_due`,
//     which can be less than `total` after a cancelled line) is shown as
//     due, never as paid. A cash payment row appears only once the server
//     records one, and is labelled from its own status.
//   - online: the order/payment status is shown as the server has it. A
//     redirect back from the provider is never proof of payment. FVS-027
//     (phase 5F): bounded verification and "Retry payment" (only while
//     can_retry_payment) live in OrderPaymentSection.
//   - cancel / confirm receipt / report a problem (FVS-031, phase 5G) are
//     the page's `customerActions` slot, kept apart from payment.
//   - no download for STL lines (ADR-019).
export function OrderDetailView({ order, pickup, paymentControls, customerActions }: OrderDetailViewProps) {
  const status = describeOrderStatus(order.status);
  const awaitingPayment = order.status === "pending_payment";

  return (
    <article aria-labelledby="order-heading" className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <Link href="/account/orders" className="self-start text-body text-brand-dark-green underline">
          Back to your orders
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 id="order-heading" className="text-h1 font-bold text-text-primary">
            Order {order.orderNumber}
          </h1>
          <StatusBadge label={status.label} tone={status.tone} />
        </div>
        <p className="text-body text-text-secondary">Placed {formatOrderDateTime(order.placedAt)}</p>
        {order.completedAt && (
          <p className="text-body text-text-secondary">Completed {formatOrderDate(order.completedAt)}</p>
        )}
        {order.cancelledAt && (
          <p className="text-body text-text-secondary">Cancelled {formatOrderDate(order.cancelledAt)}</p>
        )}
      </header>

      <div className="flex flex-col gap-6 tablet:flex-row tablet:items-start">
        <div className="flex min-w-0 flex-1 flex-col gap-6">
          <Section title="Items">
            <ul>
              {order.lines.map((line) => (
                <li key={line.id}>
                  <OrderLineItem line={line} awaitingPayment={awaitingPayment} />
                </li>
              ))}
            </ul>
          </Section>

          {customerActions}

          <FulfillmentSection order={order} pickup={pickup} />

          {order.customerNote && (
            <Section title="Your note">
              <p className="whitespace-pre-line text-body text-text-primary">{order.customerNote}</p>
            </Section>
          )}

          {order.history.length > 0 && (
            <Section title="Order updates">
              <StatusTimeline
                entries={order.history.map((entry) => {
                  const label = describeHistoryStatus(entry.toStatus, entry.lineProductType);
                  return {
                    label: entry.lineName === null ? `Order: ${label}` : `${entry.lineName}: ${label}`,
                    timeLabel: formatOrderDateTime(entry.at),
                  };
                })}
              />
            </Section>
          )}
        </div>

        <div className="flex flex-col gap-6 tablet:w-80 tablet:shrink-0">
          <OrderPaymentSection order={order} controls={paymentControls} />
          <TotalsSection order={order} />
          {order.refunds.length > 0 && (
            <Section title="Refunds">
              <ul className="flex flex-col gap-2">
                {order.refunds.map((refund, index) => (
                  <li key={`${refund.createdAt}-${index}`} className="flex flex-wrap justify-between gap-2 text-body">
                    <span>
                      {describeRefundKind(refund.kind)} · {describeRefundStatus(refund.status)}
                      <span className="block text-caption text-text-secondary">{formatOrderDate(refund.createdAt)}</span>
                    </span>
                    <Amount money={refund.amount} />
                  </li>
                ))}
              </ul>
            </Section>
          )}
        </div>
      </div>
    </article>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="flex flex-col gap-3 rounded-md border border-border-default bg-white p-4">
      <h2 className="text-h3 font-bold text-text-primary">{title}</h2>
      {children}
    </section>
  );
}

function Amount({ money }: { money: Money }) {
  return <PriceDisplay amountCents={money.amountCents} currency={money.currency} />;
}

function TotalsSection({ order }: { order: OrderDetailModel }) {
  return (
    <Section title="Summary">
      <dl className="flex flex-col gap-2 text-body text-text-primary">
        <div className="flex justify-between gap-2">
          <dt className="text-text-secondary">Subtotal</dt>
          <dd>
            <Amount money={order.subtotal} />
          </dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-text-secondary">Tax</dt>
          <dd>
            <Amount money={order.tax} />
          </dd>
        </div>
        <div className="flex justify-between gap-2 border-t border-border-default pt-2 font-semibold">
          <dt>Total</dt>
          <dd>
            <Amount money={order.total} />
          </dd>
        </div>
        {order.paymentDue && order.amountDue && (
          <div className="flex justify-between gap-2 font-semibold">
            <dt>Amount due</dt>
            <dd>
              <Amount money={order.amountDue} />
            </dd>
          </div>
        )}
      </dl>
      {order.hasDeliveryFeeNote && <p className="text-caption text-text-secondary">{FULFILLMENT_COPY.courierFee}</p>}
    </Section>
  );
}

function FulfillmentSection({ order, pickup }: { order: OrderDetailModel; pickup?: PickupOption }) {
  if (order.fulfillmentMethod === null) {
    return (
      <Section title="Delivery">
        <p className="text-body text-text-primary">
          This order only has STL files, so nothing is shipped. Our team emails each file to you once it&apos;s paid.
        </p>
      </Section>
    );
  }

  return (
    <Section title={order.fulfillmentMethod === "pickup" ? "Pickup" : "Delivery"}>
      {order.fulfillmentMethod === "delivery" && order.deliveryAddress && (
        <div className="text-body text-text-primary">
          <p className="font-semibold">Delivery to</p>
          {order.deliveryAddress.recipientName && <p>{order.deliveryAddress.recipientName}</p>}
          {order.deliveryAddress.lines.map((line) => (
            <p key={line} className="text-text-secondary">
              {line}
            </p>
          ))}
        </div>
      )}
      {order.fulfillmentMethod === "pickup" && (
        <div className="text-body text-text-primary">
          <p>You&apos;ll collect this order from us.</p>
          {pickup?.address && (
            <div className="mt-2">
              <p className="font-semibold">Pickup location</p>
              <p className="whitespace-pre-line text-text-secondary">{pickup.address}</p>
              {pickup.hours && <p className="whitespace-pre-line text-caption text-text-secondary">{pickup.hours}</p>}
            </div>
          )}
        </div>
      )}
      {order.contactPhone && (
        <p className="text-body text-text-primary">
          <span className="text-text-secondary">Contact phone: </span>
          {order.contactPhone}
        </p>
      )}
      {order.estimatedDispatchAt && (
        <p className="text-body text-text-primary">
          <span className="text-text-secondary">Estimated ready date: </span>
          {formatOrderDate(order.estimatedDispatchAt)}
        </p>
      )}
    </Section>
  );
}
