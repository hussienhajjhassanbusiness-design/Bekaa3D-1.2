import Link from "next/link";
import type { Ref } from "react";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { Button, buttonLinkClassName } from "@/components/forms/Button";
import { Icon } from "@/components/ui/Icon";
import { FULFILLMENT_COPY } from "@/lib/checkout/checkoutCopy";
import type { PickupOption } from "@/lib/checkout/checkoutEligibility";
import type { CheckoutResultModel } from "@/lib/checkout/checkoutModel";
import { CheckoutLineIssues } from "./CheckoutLineIssues";
import { OrderSummary } from "./OrderSummary";

export interface CheckoutConfirmationProps {
  result: CheckoutResultModel;
  // productId -> name from the cart as submitted, to name dropped lines.
  names: Readonly<Record<string, string>>;
  pickup: PickupOption;
  onContinueToPayment: () => void;
  headingRef?: Ref<HTMLHeadingElement>;
}

const UNKNOWN_PRODUCT = "An STL file";
const CARD_CLASSES =
  "rounded-card border border-outline-variant/30 bg-surface-container-lowest p-5 shadow-sm tablet:p-8";

function formatDate(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", { dateStyle: "long" }).format(new Date(iso));
}

// #FVS026-CHECKOUT-RESULT
//
// Shows only what the 201 CheckoutRead says. A cash order is placed and
// unpaid (payment_due, amount_due): it is never called paid. An online
// order is pending_payment with a pending payment: this screen appears only
// when it is not redirected straight to the payment page (an already-owned
// STL was dropped, or there is no usable redirect_url), and never claims
// the payment succeeded. Payment results are FVS-027.
//
// Phase 5E: "View order" opens the real order page (/account/orders/{id},
// GET /me/orders/{id}), which shows the server's current state.
//
// Redesign Batch 6: a result card (cash = check glyph, online = "continues
// on another page" glyph — an unpaid order is never given a success
// treatment), mono order number, the amount due / payment-page callout,
// then the server's lines and totals and the fulfillment in cards. Every
// figure is still a CheckoutRead value; nothing is summed here.
export function CheckoutConfirmation({
  result,
  names,
  pickup,
  onContinueToPayment,
  headingRef,
}: CheckoutConfirmationProps) {
  const cash = result.paymentMethod === "cash";
  const dropped = result.droppedProductIds.map((productId) => ({
    productId,
    name: names[productId] ?? UNKNOWN_PRODUCT,
  }));

  return (
    <section aria-labelledby="checkout-result-heading" className="flex max-w-3xl flex-col gap-6">
      <div className={CARD_CLASSES}>
        <div className="flex items-start gap-4">
          <span
            aria-hidden="true"
            className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full ${
              cash ? "bg-secondary-container text-on-secondary-container" : "bg-surface-container text-primary"
            }`}
          >
            <Icon name={cash ? "check-circle" : "open-in-new"} className="h-6 w-6" />
          </span>
          <div className="flex min-w-0 flex-col gap-1">
            <h2
              id="checkout-result-heading"
              ref={headingRef}
              tabIndex={-1}
              className="break-words font-headline text-headline-lg text-on-surface outline-none"
            >
              {cash ? "Order placed" : "Your order is awaiting payment"}
            </h2>
            <p className="text-body-md text-on-surface-variant">
              Order number{" "}
              <span className="font-label text-label-caps font-bold tracking-wider text-on-surface">
                {result.orderNumber}
              </span>
            </p>
          </div>
        </div>
        <div className="mt-6 flex flex-col gap-3">
          {cash ? <CashDue result={result} /> : <OnlineDue result={result} onContinueToPayment={onContinueToPayment} />}
        </div>
      </div>

      {dropped.length > 0 && (
        <CheckoutLineIssues
          message="These STL files were not included in your order because you already own them. You weren't charged for them:"
          items={dropped}
        />
      )}

      <section aria-label="Order items" className={`${CARD_CLASSES} flex flex-col gap-5`}>
        <ul className="flex flex-col divide-y divide-outline-variant/30">
          {result.lines.map((line) => (
            <li
              key={line.id}
              className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-3 text-body-md text-on-surface first:pt-0"
            >
              <span className="min-w-0 break-words">
                {line.name} <span className="text-on-surface-variant">× {line.quantity}</span>
              </span>
              <span className="font-label text-label-caps font-bold tabular-nums">
                <PriceDisplay amountCents={line.lineTotal.amountCents} currency={line.lineTotal.currency} />
              </span>
            </li>
          ))}
        </ul>
        <div className="border-t border-outline-variant/40 pt-5">
          <OrderSummary
            subtotalCents={result.subtotal.amountCents}
            totalCents={result.total.amountCents}
            currency={result.total.currency}
            emphasis
          />
        </div>
      </section>

      <FulfillmentSummary result={result} pickup={pickup} />

      <div className="flex flex-wrap gap-3">
        <Link href={`/account/orders/${encodeURIComponent(result.orderId)}`} className={buttonLinkClassName("primary")}>
          View order
        </Link>
        <Link href="/shop" className={buttonLinkClassName("outline")}>
          Continue shopping
        </Link>
      </div>
    </section>
  );
}

function CashDue({ result }: { result: CheckoutResultModel }) {
  const where = result.fulfillmentMethod === "pickup" ? "when you pick up your order" : "to the courier on delivery";
  return (
    <>
      {result.paymentDue && result.amountDue && (
        <p className="rounded-card border border-info-outline bg-info-container p-4 text-sm text-on-info-container">
          Payment due in cash {where}:{" "}
          <span className="font-semibold">
            <PriceDisplay amountCents={result.amountDue.amountCents} currency={result.amountDue.currency} />
          </span>
          . This order hasn&apos;t been paid yet.
        </p>
      )}
      <p className="flex items-center gap-2 text-sm text-on-surface-variant">
        <Icon name="mail" className="h-4 w-4" />
        We&apos;ve sent the order details to your email.
      </p>
    </>
  );
}

function OnlineDue({ result, onContinueToPayment }: { result: CheckoutResultModel; onContinueToPayment: () => void }) {
  if (result.next === "online-redirect") {
    return (
      <div className="flex flex-col items-start gap-3">
        <p className="text-body-md text-on-surface">
          Nothing has been paid yet. Continue to the payment page to pay for this order.
        </p>
        <Button type="button" onClick={onContinueToPayment}>
          Continue to payment
        </Button>
      </div>
    );
  }
  return (
    <p
      role="alert"
      className="rounded-card border border-warning-outline bg-warning-container p-4 text-sm text-on-warning-container"
    >
      The payment page isn&apos;t available right now, so nothing has been charged. Please contact us to complete this
      order.
    </p>
  );
}

function FulfillmentSummary({ result, pickup }: { result: CheckoutResultModel; pickup: PickupOption }) {
  if (result.fulfillmentMethod === null) {
    return (
      <p className="flex items-start gap-3 rounded-card bg-surface-container-low p-4 text-sm text-on-surface">
        <Icon name="mail" className="mt-px h-5 w-5 text-primary" />
        <span>{FULFILLMENT_COPY.digitalOnly}</span>
      </p>
    );
  }
  return (
    <section
      aria-label="Fulfillment"
      className={`${CARD_CLASSES} flex flex-col gap-3 break-words text-body-md text-on-surface`}
    >
      {result.fulfillmentMethod === "delivery" && result.deliveryAddress && (
        <div className="flex items-start gap-3">
          <Icon name="local-shipping" className="mt-0.5 h-5 w-5 text-primary" />
          <div className="min-w-0">
            <p className="font-label text-label-caps uppercase text-on-surface-variant">Delivery to</p>
            <p className="mt-1">{result.deliveryAddress.recipientName}</p>
            {result.deliveryAddress.lines.map((line) => (
              <p key={line} className="text-on-surface-variant">
                {line}
              </p>
            ))}
            <p className="mt-2 text-xs text-on-surface-variant">{FULFILLMENT_COPY.courierFee}</p>
          </div>
        </div>
      )}
      {result.fulfillmentMethod === "pickup" && (
        <div className="flex items-start gap-3">
          <Icon name="storefront" className="mt-0.5 h-5 w-5 text-primary" />
          <div className="min-w-0">
            <p className="font-label text-label-caps uppercase text-on-surface-variant">Pickup</p>
            {pickup.address && <p className="mt-1 whitespace-pre-line text-on-surface-variant">{pickup.address}</p>}
            {pickup.hours && <p className="whitespace-pre-line text-xs text-on-surface-variant">{pickup.hours}</p>}
          </div>
        </div>
      )}
      {result.estimatedDispatchAt && (
        <p className="flex items-center gap-2 border-t border-outline-variant/30 pt-3 text-on-surface-variant">
          <Icon name="schedule" className="h-4 w-4" />
          Estimated dispatch: {formatDate(result.estimatedDispatchAt)}.
        </p>
      )}
    </section>
  );
}
