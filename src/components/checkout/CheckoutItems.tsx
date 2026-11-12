import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { UNNAMED_PRODUCT, type CartModel } from "@/lib/cart/cartModel";

// #FVS026-CHECKOUT-ITEMS
//
// The canonical cart as the server returned it. Unit prices only: CartRead
// has no line total, subtotal or order total, and checkout charges live
// prices, so no figure is summed here. The current price is shown when the
// server has one; a server-flagged price change is labelled, never
// reconciled on the client.
export function CheckoutItems({ cart }: { cart: CartModel }) {
  return (
    <section aria-labelledby="checkout-items-heading" className="flex flex-col gap-3">
      <h2 id="checkout-items-heading" className="text-h4 font-semibold text-text-primary">
        Your items
      </h2>
      <ul className="flex flex-col divide-y divide-border-default rounded-md border border-border-default bg-white">
        {cart.lines.map((line) => {
          const price = line.currentPrice ?? line.snapshotPrice;
          return (
            <li key={line.productId} className="flex flex-wrap items-start justify-between gap-2 p-3">
              <div>
                <p className="text-body font-semibold text-text-primary">{line.name ?? UNNAMED_PRODUCT}</p>
                <p className="text-caption text-text-secondary">
                  {line.productType === "stl" ? "STL file (sent by email)" : "Physical item"} · Qty {line.quantity}
                </p>
                {line.priceChanged && <p className="text-caption font-semibold text-warning-text">Price updated</p>}
              </div>
              <p className="text-body text-text-primary">
                <PriceDisplay amountCents={price.amountCents} currency={price.currency} />
                <span className="text-caption text-text-secondary"> each</span>
              </p>
            </li>
          );
        })}
      </ul>
      <p className="text-caption text-text-secondary">
        Your order total is calculated from current prices when you place your order, and shown on the next screen.
      </p>
    </section>
  );
}
