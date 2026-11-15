import type { ReactNode } from "react";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { Icon } from "@/components/ui/Icon";
import { UNNAMED_PRODUCT, type CartModel } from "@/lib/cart/cartModel";

export interface CheckoutItemsProps {
  cart: CartModel;
  // Rendered at the bottom of the summary card (the Place order action).
  children?: ReactNode;
}

// #FVS026-CHECKOUT-ITEMS
//
// The canonical cart as the server returned it. Unit prices only: CartRead
// has no line total, subtotal or order total, and checkout charges live
// prices, so no figure is summed here. The current price is shown when the
// server has one; a server-flagged price change is labelled, never
// reconciled on the client.
//
// Redesign Batch 6: the Stitch checkout Order Summary card (COMPONENT-SPECS
// §35): white 16px panel, thumbnail rows, mono prices. The Stitch
// subtotal / shipping / tax / total rows are deliberately absent — the
// cart has none of those values and ADR-024 forbids a shipping charge —
// and are replaced by the honest "calculated when you place your order"
// note. The real server totals appear on the confirmation (OrderSummary).
export function CheckoutItems({ cart, children }: CheckoutItemsProps) {
  return (
    <section
      aria-labelledby="checkout-items-heading"
      className="flex flex-col gap-6 rounded-panel border border-outline-variant/40 bg-surface-container-lowest p-5 shadow-sm tablet:p-8"
    >
      <h2 id="checkout-items-heading" className="font-headline text-headline-md text-on-surface">
        Order summary
      </h2>
      <ul className="flex flex-col gap-5">
        {cart.lines.map((line) => {
          const price = line.currentPrice ?? line.snapshotPrice;
          const isStl = line.productType === "stl";
          return (
            <li key={line.productId} className="flex min-w-0 items-start gap-4">
              <div className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-control bg-surface-container tablet:h-20 tablet:w-20">
                {line.coverImage ? (
                  // Decorative here: the product name is right beside it.
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={line.coverImage.src} alt="" className="h-full w-full object-cover" />
                ) : (
                  <Icon name={isStl ? "deployed-code" : "image"} className="h-7 w-7 text-outline" strokeWidth={1.5} />
                )}
              </div>
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
                  <p className="min-w-0 break-words font-headline text-title-sm text-on-surface">
                    {line.name ?? UNNAMED_PRODUCT}
                  </p>
                  <p className="font-label text-label-caps font-bold tabular-nums text-primary">
                    <PriceDisplay amountCents={price.amountCents} currency={price.currency} />
                    <span className="font-body text-xs font-normal text-on-surface-variant"> each</span>
                  </p>
                </div>
                <p className="text-xs text-on-surface-variant">
                  {isStl ? "STL file (sent by email)" : "Physical item"} · Qty {line.quantity}
                </p>
                {line.priceChanged && (
                  <p className="flex items-center gap-1.5 text-xs font-semibold text-on-warning-container">
                    <Icon name="warning" className="h-4 w-4" />
                    Price updated
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ul>
      <p className="flex items-start gap-2 border-t border-outline-variant/40 pt-5 text-xs text-on-surface-variant">
        <Icon name="receipt-long" className="mt-px h-4 w-4 text-outline" />
        <span>
          Your order total is calculated from current prices when you place your order, and shown on the next screen.
        </span>
      </p>
      {children}
    </section>
  );
}
