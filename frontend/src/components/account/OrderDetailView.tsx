import type { ReactNode } from "react";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { Icon, type IconName } from "@/components/ui/Icon";
import { PageHeader } from "@/components/ui/PageHeader";
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
import { ACCOUNT_TERM, AccountBackLink, AccountSection } from "./accountUi";
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
  // FVS-031: the page's "Order actions" section (OrderCustomerActions).
  // Absent, the view stays read-only.
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
//
// Batch 7 (DERIVED: no Stitch order-detail screen; account shell +
// PageHeader + Stitch card/status language). The h1 and the order status
// pill share one parent (PageHeader `meta`), which E2E reads. Order of the
// page, one column (DOM order = visual order = keyboard order): payment and
// totals first (side by side from 1280px), refunds, the customer's
// actions, then items, fulfilment / note and the long update history last,
// so nothing actionable sits below long secondary information.
export function OrderDetailView({ order, pickup, paymentControls, customerActions }: OrderDetailViewProps) {
  const status = describeOrderStatus(order.status);
  const awaitingPayment = order.status === "pending_payment";

  return (
    <article aria-labelledby="order-heading" className="flex min-w-0 flex-col">
      <div>
        <AccountBackLink href="/account/orders">Back to your orders</AccountBackLink>
      </div>
      <PageHeader
        eyebrow="Order details"
        title={`Order ${order.orderNumber}`}
        headingId="order-heading"
        meta={<StatusBadge label={status.label} tone={status.tone} />}
        description={
          <>
            <span className="block">Placed {formatOrderDateTime(order.placedAt)}</span>
            {order.completedAt && <span className="block">Completed {formatOrderDate(order.completedAt)}</span>}
            {order.cancelledAt && <span className="block">Cancelled {formatOrderDate(order.cancelledAt)}</span>}
          </>
        }
      />

      <div className="flex min-w-0 flex-col gap-6">
        <div className="grid min-w-0 items-start gap-6 xl:grid-cols-2">
          <OrderPaymentSection order={order} controls={paymentControls} />
          <TotalsSection order={order} />
        </div>

        {order.refunds.length > 0 && (
          <AccountSection title="Refunds" icon="payments">
            <ul className="flex flex-col divide-y divide-outline-variant/30">
              {order.refunds.map((refund, index) => (
                <li
                  key={`${refund.createdAt}-${index}`}
                  className="flex flex-wrap items-start justify-between gap-2 py-3 first:pt-0 last:pb-0"
                >
                  <span className="min-w-0 text-body-md text-on-surface">
                    {describeRefundKind(refund.kind)} · {describeRefundStatus(refund.status)}
                    <span className="mt-1 block font-label text-label-caps uppercase text-on-surface-variant">
                      {formatOrderDate(refund.createdAt)}
                    </span>
                  </span>
                  <span className="font-label text-title-sm font-bold text-on-surface">
                    <Amount money={refund.amount} />
                  </span>
                </li>
              ))}
            </ul>
          </AccountSection>
        )}

        {customerActions}

        <AccountSection title="Items" icon="receipt-long">
          <ul className="flex flex-col divide-y divide-outline-variant/30">
            {order.lines.map((line) => (
              <li key={line.id} className="py-4 first:pt-0 last:pb-0">
                <OrderLineItem line={line} awaitingPayment={awaitingPayment} />
              </li>
            ))}
          </ul>
        </AccountSection>

        <div className={`grid min-w-0 items-start gap-6 ${order.customerNote ? "xl:grid-cols-2" : ""}`}>
          <FulfillmentSection order={order} pickup={pickup} />
          {order.customerNote && (
            <AccountSection title="Your note" icon="edit">
              <p className="whitespace-pre-line break-words rounded-control bg-surface-container-low p-4 text-body-md text-on-surface-variant">
                {order.customerNote}
              </p>
            </AccountSection>
          )}
        </div>

        {order.history.length > 0 && (
          <AccountSection title="Order updates" icon="schedule">
            <StatusTimeline
              entries={order.history.map((entry) => {
                const label = describeHistoryStatus(entry.toStatus, entry.lineProductType);
                return {
                  label: entry.lineName === null ? `Order: ${label}` : `${entry.lineName}: ${label}`,
                  timeLabel: formatOrderDateTime(entry.at),
                };
              })}
            />
          </AccountSection>
        )}
      </div>
    </article>
  );
}

function Amount({ money }: { money: Money }) {
  return <PriceDisplay amountCents={money.amountCents} currency={money.currency} />;
}

// Server totals only (subtotal, tax, total, amount due): nothing is summed
// here. Stitch §35 summary card: lavender panel, total in the summary role.
function TotalsSection({ order }: { order: OrderDetailModel }) {
  return (
    <AccountSection title="Summary" tinted>
      <dl className="flex flex-col gap-3 text-body-md text-on-surface-variant">
        <div className="flex justify-between gap-2">
          <dt>Subtotal</dt>
          <dd className="font-label text-on-surface">
            <Amount money={order.subtotal} />
          </dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Tax</dt>
          <dd className="font-label text-on-surface">
            <Amount money={order.tax} />
          </dd>
        </div>
        <div className="flex items-baseline justify-between gap-2 border-t border-outline-variant/60 pt-3">
          <dt className="font-headline text-headline-md text-on-surface">Total</dt>
          <dd className="font-headline text-headline-md text-on-surface">
            <Amount money={order.total} />
          </dd>
        </div>
        {order.paymentDue && order.amountDue && (
          <div className="flex items-baseline justify-between gap-2 rounded-control bg-surface-container-lowest px-3 py-2 font-semibold text-on-surface">
            <dt>Amount due</dt>
            <dd className="font-label">
              <Amount money={order.amountDue} />
            </dd>
          </div>
        )}
      </dl>
      {order.hasDeliveryFeeNote && (
        <p className="flex items-start gap-2 text-sm text-on-surface-variant">
          <Icon name="info" className="mt-0.5 h-4 w-4 shrink-0 text-info" />
          {FULFILLMENT_COPY.courierFee}
        </p>
      )}
    </AccountSection>
  );
}

function Detail({ icon, children }: { icon: IconName; children: ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <Icon name={icon} className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
      <div className="min-w-0 break-words text-body-md text-on-surface">{children}</div>
    </div>
  );
}

function FulfillmentSection({ order, pickup }: { order: OrderDetailModel; pickup?: PickupOption }) {
  if (order.fulfillmentMethod === null) {
    return (
      <AccountSection title="Delivery" icon="mail">
        <p className="text-body-md text-on-surface">
          This order only has STL files, so nothing is shipped. Our team emails each file to you once it&apos;s paid.
        </p>
      </AccountSection>
    );
  }

  const isPickup = order.fulfillmentMethod === "pickup";
  return (
    <AccountSection title={isPickup ? "Pickup" : "Delivery"} icon={isPickup ? "storefront" : "local-shipping"}>
      <div className="flex flex-col gap-4">
        {order.fulfillmentMethod === "delivery" && order.deliveryAddress && (
          <Detail icon="location-on">
            <p className={ACCOUNT_TERM}>Delivery to</p>
            {order.deliveryAddress.recipientName && (
              <p className="mt-1 font-semibold">{order.deliveryAddress.recipientName}</p>
            )}
            {order.deliveryAddress.lines.map((line) => (
              <p key={line} className="text-on-surface-variant">
                {line}
              </p>
            ))}
          </Detail>
        )}
        {isPickup && (
          <Detail icon="storefront">
            <p>You&apos;ll collect this order from us.</p>
            {pickup?.address && (
              <div className="mt-3">
                <p className={ACCOUNT_TERM}>Pickup location</p>
                <p className="mt-1 whitespace-pre-line text-on-surface-variant">{pickup.address}</p>
                {pickup.hours && (
                  <p className="mt-1 whitespace-pre-line text-sm text-on-surface-variant">{pickup.hours}</p>
                )}
              </div>
            )}
          </Detail>
        )}
        {order.contactPhone && (
          <Detail icon="call">
            <span className={ACCOUNT_TERM}>Contact phone: </span>
            <span dir="ltr" className="tabular-nums">
              {order.contactPhone}
            </span>
          </Detail>
        )}
        {order.estimatedDispatchAt && (
          <Detail icon="schedule">
            <span className={ACCOUNT_TERM}>Estimated ready date: </span>
            {formatOrderDate(order.estimatedDispatchAt)}
          </Detail>
        )}
      </div>
    </AccountSection>
  );
}
