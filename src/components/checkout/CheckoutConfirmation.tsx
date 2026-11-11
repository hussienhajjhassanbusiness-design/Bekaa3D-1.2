import Link from "next/link";
import type { Ref } from "react";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { Button } from "@/components/forms/Button";
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
    <section aria-labelledby="checkout-result-heading" className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h2 id="checkout-result-heading" ref={headingRef} tabIndex={-1} className="text-h2 font-bold text-text-primary">
          {cash ? "Order placed" : "Your order is awaiting payment"}
        </h2>
        <p className="text-body text-text-primary">
          Order number <span className="font-semibold">{result.orderNumber}</span>
        </p>
        {cash ? <CashDue result={result} /> : <OnlineDue result={result} onContinueToPayment={onContinueToPayment} />}
      </div>

      {dropped.length > 0 && (
        <CheckoutLineIssues
          message="These STL files were not included in your order because you already own them. You weren't charged for them:"
          items={dropped}
        />
      )}

      <section
        aria-label="Order items"
        className="flex flex-col gap-3 rounded-md border border-border-default bg-white p-4"
      >
        <ul className="flex flex-col gap-2">
          {result.lines.map((line) => (
            <li key={line.id} className="flex flex-wrap items-center justify-between gap-2 text-body text-text-primary">
              <span>
                {line.name} <span className="text-text-secondary">× {line.quantity}</span>
              </span>
              <PriceDisplay amountCents={line.lineTotal.amountCents} currency={line.lineTotal.currency} />
            </li>
          ))}
        </ul>
        <OrderSummary
          subtotalCents={result.subtotal.amountCents}
          totalCents={result.total.amountCents}
          currency={result.total.currency}
        />
      </section>

      <FulfillmentSummary result={result} pickup={pickup} />

      <div className="flex flex-wrap gap-4">
        <Link
          href={`/account/orders/${encodeURIComponent(result.orderId)}`}
          className="font-semibold text-brand-dark-green underline"
        >
          View order
        </Link>
        <Link href="/shop" className="font-semibold text-brand-dark-green underline">
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
        <p className="rounded-md border-l-4 border-l-info bg-info-bg p-3 text-body text-text-primary">
          Payment due in cash {where}:{" "}
          <span className="font-semibold">
            <PriceDisplay amountCents={result.amountDue.amountCents} currency={result.amountDue.currency} />
          </span>
          . This order hasn&apos;t been paid yet.
        </p>
      )}
      <p className="text-body text-text-secondary">We&apos;ve sent the order details to your email.</p>
    </>
  );
}

function OnlineDue({ result, onContinueToPayment }: { result: CheckoutResultModel; onContinueToPayment: () => void }) {
  if (result.next === "online-redirect") {
    return (
      <div className="flex flex-col items-start gap-3">
        <p className="text-body text-text-primary">
          Nothing has been paid yet. Continue to the payment page to pay for this order.
        </p>
        <Button type="button" onClick={onContinueToPayment}>
          Continue to payment
        </Button>
      </div>
    );
  }
  return (
    <p role="alert" className="rounded-md border-l-4 border-l-warning bg-warning-bg p-3 text-body text-text-primary">
      The payment page isn&apos;t available right now, so nothing has been charged. Please contact us to complete this
      order.
    </p>
  );
}

function FulfillmentSummary({ result, pickup }: { result: CheckoutResultModel; pickup: PickupOption }) {
  if (result.fulfillmentMethod === null) {
    return <p className="text-body text-text-secondary">{FULFILLMENT_COPY.digitalOnly}</p>;
  }
  return (
    <section aria-label="Fulfillment" className="flex flex-col gap-2 text-body text-text-primary">
      {result.fulfillmentMethod === "delivery" && result.deliveryAddress && (
        <div>
          <p className="font-semibold">Delivery to</p>
          <p>{result.deliveryAddress.recipientName}</p>
          {result.deliveryAddress.lines.map((line) => (
            <p key={line} className="text-text-secondary">
              {line}
            </p>
          ))}
          <p className="mt-2 text-caption text-text-secondary">{FULFILLMENT_COPY.courierFee}</p>
        </div>
      )}
      {result.fulfillmentMethod === "pickup" && (
        <div>
          <p className="font-semibold">Pickup</p>
          {pickup.address && <p className="whitespace-pre-line text-text-secondary">{pickup.address}</p>}
          {pickup.hours && <p className="whitespace-pre-line text-caption text-text-secondary">{pickup.hours}</p>}
        </div>
      )}
      {result.estimatedDispatchAt && (
        <p className="text-text-secondary">Estimated dispatch: {formatDate(result.estimatedDispatchAt)}.</p>
      )}
    </section>
  );
}
