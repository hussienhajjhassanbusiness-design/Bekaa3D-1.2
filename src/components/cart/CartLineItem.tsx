import Link from "next/link";
import { useId, type ReactNode } from "react";
import { Button } from "@/components/forms/Button";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { ProductTypeBadge } from "@/components/catalog/ProductTypeBadge";
import { Icon, type IconName } from "@/components/ui/Icon";
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

// Stitch pill stepper (COMPONENT-SPECS §26) at a 44px target size.
const STEP_BUTTON_CLASSES =
  "flex h-11 w-11 items-center justify-center rounded-full text-on-surface transition-colors duration-200 ease-standard " +
  "enabled:hover:bg-surface-container-highest enabled:hover:text-primary disabled:cursor-not-allowed disabled:opacity-40 " +
  "motion-reduce:transition-none";

// #FVS025-CART-LINE-ITEM
//
// Presentational only. Every figure is a CartLineRead value: the unit price
// is `snapshot_price` (the price when the line was added, display only),
// and a server-flagged `price_changed` shows `current_price` beside it.
// There is no line total, because the contract has none and checkout
// charges live prices. STL lines never get a stepper. The physical
// stepper is bounded by the server's `max_quantity` and sends absolute
// quantities; the server still decides.
//
// Redesign Batch 6 (COMPONENT-SPECS §36): white line card, 128px media
// tile, type tag, title, notices as tinted callouts with an icon AND text
// (never colour alone), pill stepper + price on the right from 768px.
export function CartLineItem({ line, pending = false, errorMessage, onQuantityChange, onRemove }: CartLineItemProps) {
  const titleId = useId();
  const name = line.name ?? UNNAMED_PRODUCT;
  const control = quantityControl(line);
  const isStl = line.productType === "stl";
  const showStepper = line.productType === "physical" && line.purchasable;
  const blocked = !line.purchasable || line.overCap;

  return (
    <article
      aria-labelledby={titleId}
      aria-busy={pending}
      className={`flex flex-col gap-5 rounded-card border bg-surface-container-lowest p-5 shadow-sm tablet:flex-row tablet:gap-6 tablet:p-6 ${
        blocked ? "border-error/40" : "border-outline-variant/30"
      }`}
    >
      <div
        className={`flex h-32 w-full shrink-0 items-center justify-center overflow-hidden rounded-control bg-surface-container-low tablet:w-32 ${
          line.purchasable ? "" : "opacity-60"
        }`}
      >
        {line.coverImage ? (
          // Plain <img>, matching ProductCard: the media host is not a
          // configured next/image remote pattern.
          // eslint-disable-next-line @next/next/no-img-element
          <img src={line.coverImage.src} alt={line.coverImage.alt} className="h-full w-full object-cover" />
        ) : (
          <Icon name={isStl ? "deployed-code" : "image"} className="h-10 w-10 text-outline" strokeWidth={1.5} />
        )}
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-4">
        <div className="flex flex-col gap-4 tablet:flex-row tablet:items-start tablet:justify-between">
          <div className="flex min-w-0 flex-col items-start gap-2">
            <ProductTypeBadge type={line.productType} />
            <h2 id={titleId} className="break-words font-headline text-title-sm text-on-surface">
              {line.slug ? (
                <Link
                  href={`/shop/${line.slug}`}
                  className="rounded-sm transition-colors duration-200 hover:text-primary hover:underline motion-reduce:transition-none"
                >
                  {name}
                </Link>
              ) : (
                name
              )}
            </h2>
          </div>

          <LinePrice line={line} />
        </div>

        {line.priceChanged && (
          <LineNotice tone="warning" icon="warning">
            The price has changed since you added it. Checkout uses the current price.
          </LineNotice>
        )}

        {!line.purchasable && line.unpurchasableReason && (
          <LineNotice tone="error" icon="error">
            {REFUSAL_COPY[line.unpurchasableReason]}
          </LineNotice>
        )}

        {line.purchasable && line.overCap && control.reduceToCap !== null && (
          <LineNotice tone="warning" icon="warning">
            <span className="flex flex-wrap items-center gap-3">
              <span>You can order at most {control.reduceToCap} of this product per order now.</span>
              <Button
                type="button"
                variant="secondary"
                disabled={pending}
                onClick={() => onQuantityChange(line.productId, control.reduceToCap!)}
                aria-label={`Reduce ${name} to ${control.reduceToCap}`}
              >
                Reduce to {control.reduceToCap}
              </Button>
            </span>
          </LineNotice>
        )}

        <div className="mt-auto flex flex-wrap items-center justify-between gap-3 border-t border-outline-variant/30 pt-4">
          {showStepper ? (
            <div className="flex flex-col gap-1">
              <div
                className="flex w-fit items-center rounded-full border border-outline-variant/40 bg-surface-container-high p-0.5"
                role="group"
                aria-label={`Quantity of ${name}`}
              >
                <button
                  type="button"
                  className={STEP_BUTTON_CLASSES}
                  onClick={() => onQuantityChange(line.productId, line.quantity - 1)}
                  disabled={pending || !control.canDecrease}
                  aria-label={`Decrease quantity of ${name}`}
                >
                  <Icon name="remove" className="h-5 w-5" />
                </button>
                <span
                  aria-live="polite"
                  className="min-w-10 text-center font-label text-label-caps font-bold tabular-nums text-on-surface"
                >
                  {line.quantity}
                </span>
                <button
                  type="button"
                  className={STEP_BUTTON_CLASSES}
                  onClick={() => onQuantityChange(line.productId, line.quantity + 1)}
                  disabled={pending || !control.canIncrease}
                  aria-label={`Increase quantity of ${name}`}
                >
                  <Icon name="add" className="h-5 w-5" />
                </button>
              </div>
              {line.maxQuantity !== null && !line.overCap && (
                <p className="text-caption text-on-surface-variant">Maximum {line.maxQuantity} per order</p>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              <p className="font-label text-label-caps uppercase text-on-surface-variant">Quantity: {line.quantity}</p>
              {isStl && <p className="text-caption text-on-surface-variant">STL files are sold one copy per order.</p>}
            </div>
          )}

          <button
            type="button"
            onClick={() => onRemove(line.productId)}
            disabled={pending}
            aria-label={`Remove ${name} from cart`}
            className="-mr-2 inline-flex min-h-11 items-center gap-2 rounded-control px-3 text-body font-medium text-on-surface-variant transition-colors duration-200 ease-standard enabled:hover:bg-error-container/60 enabled:hover:text-error disabled:cursor-not-allowed disabled:opacity-50 motion-reduce:transition-none"
          >
            <Icon name="delete" className="h-5 w-5" />
            Remove
          </button>
        </div>

        {pending && <p className="sr-only">Updating {name}…</p>}

        {errorMessage && (
          <p role="alert" className="flex items-start gap-2 text-caption text-error">
            <Icon name="error" className="mt-px h-4 w-4" />
            <span className="min-w-0">{errorMessage}</span>
          </p>
        )}
      </div>
    </article>
  );
}

// Unit price only. A server-flagged change shows both values with visible
// labels; the strike-through is decoration, the labels carry the meaning.
function LinePrice({ line }: { line: CartLineModel }) {
  const changed = line.priceChanged && line.currentPrice !== null;
  return (
    <div className="flex shrink-0 flex-col gap-1 tablet:items-end tablet:text-right">
      <p className="font-label text-label-sm uppercase tracking-widest text-on-surface-variant">
        {line.priceChanged ? "Price when added" : "Price"}
      </p>
      <p
        className={
          changed
            ? "text-body-md text-on-surface-variant line-through decoration-1"
            : "font-headline text-headline-md tabular-nums text-on-surface"
        }
      >
        <PriceDisplay amountCents={line.snapshotPrice.amountCents} currency={line.snapshotPrice.currency} />
      </p>
      {changed && (
        <>
          <p className="mt-1 font-label text-label-sm uppercase tracking-widest text-on-surface-variant">
            Current price
          </p>
          <p className="font-headline text-headline-md tabular-nums text-on-surface">
            <PriceDisplay amountCents={line.currentPrice!.amountCents} currency={line.currentPrice!.currency} />
          </p>
        </>
      )}
    </div>
  );
}

const NOTICE_TONES = {
  warning: {
    box: "border-warning-outline bg-warning-container text-on-warning-container",
    icon: "text-on-warning-container",
  },
  error: {
    box: "border-error/20 bg-error-container text-on-error-container",
    icon: "text-error",
  },
} as const;

function LineNotice({
  tone,
  icon,
  children,
}: {
  tone: keyof typeof NOTICE_TONES;
  icon: IconName;
  children: ReactNode;
}) {
  return (
    <div className={`flex items-start gap-2 rounded-control border px-3 py-2 text-caption ${NOTICE_TONES[tone].box}`}>
      <Icon name={icon} className={`mt-px h-4 w-4 ${NOTICE_TONES[tone].icon}`} />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
