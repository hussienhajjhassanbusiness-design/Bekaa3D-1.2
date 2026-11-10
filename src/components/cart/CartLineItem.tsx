import Link from "next/link";
import { useId } from "react";
import { Button } from "@/components/forms/Button";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { ProductTypeBadge } from "@/components/catalog/ProductTypeBadge";
import { quantityControl } from "@/lib/cart/cartInvariants";
import { UNNAMED_PRODUCT, type CartLineModel } from "@/lib/cart/cartModel";
import type { PurchaseRefusal } from "@/lib/cart/cartTypes";

export interface CartLineItemProps {
  line: CartLineModel;
  // A write for this line is in flight: every control is disabled until
  // the server answers (no optimistic quantity, no double submits).
  pending?: boolean;
  // Already-safe, frontend-owned copy (describeCartWriteError).
  errorMessage?: string;
  // Absolute quantity, as PATCH /cart/items/{product_id} expects.
  onQuantityChange: (productId: string, quantity: number) => void;
  onRemove: (productId: string) => void;
}

const REFUSAL_COPY: Readonly<Record<PurchaseRefusal, string>> = {
  unavailable: "This product is currently unavailable. Remove it to check out.",
  whatsapp_only: "This product can now only be ordered through WhatsApp. Remove it to check out.",
  not_listed: "This product is no longer available. Remove it to check out.",
};

// #FVS025-CART-LINE-ITEM
//
// Presentational only. Every figure is a CartLineRead value: the unit price
// is `snapshot_price` (the price when the line was added, display only),
// and a server-flagged `price_changed` shows `current_price` beside it.
// There is no line total, because the contract has none and checkout
// charges live prices. STL lines never get a stepper. The physical
// stepper is bounded by the server's `max_quantity` and sends absolute
// quantities; the server still decides.
export function CartLineItem({ line, pending = false, errorMessage, onQuantityChange, onRemove }: CartLineItemProps) {
  const titleId = useId();
  const name = line.name ?? UNNAMED_PRODUCT;
  const control = quantityControl(line);
  const isStl = line.productType === "stl";
  const showStepper = line.productType === "physical" && line.purchasable;

  return (
    <article
      aria-labelledby={titleId}
      aria-busy={pending}
      className="flex flex-col gap-4 rounded-md border border-border-default bg-white p-4 tablet:flex-row"
    >
      <div className="h-24 w-24 shrink-0 overflow-hidden rounded-md bg-neutral-100">
        {line.coverImage && (
          // Plain <img>, matching ProductCard: the media host is not a
          // configured next/image remote pattern.
          // eslint-disable-next-line @next/next/no-img-element
          <img src={line.coverImage.src} alt={line.coverImage.alt} className="h-full w-full object-cover" />
        )}
      </div>

      <div className="flex flex-1 flex-col gap-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="flex flex-col gap-1">
            <h2 id={titleId} className="text-h4 font-semibold text-text-primary">
              {line.slug ? (
                <Link href={`/shop/${line.slug}`} className="hover:text-brand-dark-green hover:underline">
                  {name}
                </Link>
              ) : (
                name
              )}
            </h2>
            <div>
              <ProductTypeBadge type={line.productType} />
            </div>
          </div>

          <div className="text-right">
            <p className="text-caption text-text-secondary">{line.priceChanged ? "Price when added" : "Price"}</p>
            <p className="text-body font-semibold text-text-primary">
              <PriceDisplay amountCents={line.snapshotPrice.amountCents} currency={line.snapshotPrice.currency} />
            </p>
            {line.priceChanged && line.currentPrice && (
              <>
                <p className="mt-1 text-caption text-text-secondary">Current price</p>
                <p className="text-body font-semibold text-text-primary">
                  <PriceDisplay amountCents={line.currentPrice.amountCents} currency={line.currentPrice.currency} />
                </p>
              </>
            )}
          </div>
        </div>

        {line.priceChanged && (
          <p className="rounded-md border-l-4 border-l-warning bg-warning-bg px-3 py-2 text-caption text-text-primary">
            The price has changed since you added it. Checkout uses the current price.
          </p>
        )}

        {!line.purchasable && line.unpurchasableReason && (
          <p className="rounded-md border-l-4 border-l-danger bg-danger-bg px-3 py-2 text-caption text-text-primary">
            {REFUSAL_COPY[line.unpurchasableReason]}
          </p>
        )}

        {line.purchasable && line.overCap && control.reduceToCap !== null && (
          <div className="flex flex-wrap items-center gap-2 rounded-md border-l-4 border-l-warning bg-warning-bg px-3 py-2">
            <p className="text-caption text-text-primary">
              You can order at most {control.reduceToCap} of this product per order now.
            </p>
            <Button
              type="button"
              variant="secondary"
              className="px-3 py-1 text-caption"
              disabled={pending}
              onClick={() => onQuantityChange(line.productId, control.reduceToCap!)}
              aria-label={`Reduce ${name} to ${control.reduceToCap}`}
            >
              Reduce to {control.reduceToCap}
            </Button>
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3">
          {showStepper ? (
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-2" role="group" aria-label={`Quantity of ${name}`}>
                <Button
                  type="button"
                  variant="secondary"
                  className="h-10 w-10 px-0 py-0"
                  onClick={() => onQuantityChange(line.productId, line.quantity - 1)}
                  disabled={pending || !control.canDecrease}
                  aria-label={`Decrease quantity of ${name}`}
                >
                  −
                </Button>
                <span aria-live="polite" className="min-w-8 text-center text-body font-semibold text-text-primary">
                  {line.quantity}
                </span>
                <Button
                  type="button"
                  variant="secondary"
                  className="h-10 w-10 px-0 py-0"
                  onClick={() => onQuantityChange(line.productId, line.quantity + 1)}
                  disabled={pending || !control.canIncrease}
                  aria-label={`Increase quantity of ${name}`}
                >
                  +
                </Button>
              </div>
              {line.maxQuantity !== null && !line.overCap && (
                <p className="text-caption text-text-secondary">Maximum {line.maxQuantity} per order</p>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              <p className="text-body text-text-primary">Quantity: {line.quantity}</p>
              {isStl && <p className="text-caption text-text-secondary">STL files are sold one copy per order.</p>}
            </div>
          )}

          <Button
            type="button"
            variant="secondary"
            onClick={() => onRemove(line.productId)}
            disabled={pending}
            aria-label={`Remove ${name} from cart`}
          >
            Remove
          </Button>
        </div>

        {pending && <p className="sr-only">Updating {name}…</p>}

        {errorMessage && (
          <p role="alert" className="text-caption text-danger">
            {errorMessage}
          </p>
        )}
      </div>
    </article>
  );
}
