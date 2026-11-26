import Link from "next/link";
import { Alert } from "@/components/feedback/Alert";
import { Button, buttonLinkClassName } from "@/components/forms/Button";
import { EmptyState } from "@/components/feedback/EmptyState";
import { Icon } from "@/components/ui/Icon";
import { cartBlockingLines } from "@/lib/cart/cartInvariants";
import { cartItemCount, type CartModel } from "@/lib/cart/cartModel";
import { CartLineItem } from "./CartLineItem";

export interface CartPageProps {
  cart: CartModel | null;
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
  onQuantityChange: (productId: string, quantity: number) => void;
  onRemove: (productId: string) => void;
  pendingProductIds?: ReadonlySet<string>;
  // productId -> safe message. A message for a product no longer in the
  // cart (e.g. it was removed in another tab) is shown at the page top.
  lineErrors?: Readonly<Record<string, string>>;
  // Page-level, already-safe info copy (e.g. email verification).
  notice?: string;
  // False when the account cannot check out yet (an unverified email).
  canCheckout?: boolean;
}

const NO_PENDING: ReadonlySet<string> = new Set();

// 8/4 split from 1024px (PAGE-SPECS S6); one column below.
const GRID_CLASSES = "grid grid-cols-1 items-start gap-gutter desktop:grid-cols-12";

// #FVS025-CART-PAGE
//
// Presentational: loading / error / empty / populated. The summary has a
// unit count only. CartRead has no total, so none is shown or computed;
// checkout recomputes it from live prices. Phase 5D: the checkout CTA links
// to /checkout (FVS-026) only when the cart can proceed; otherwise it is a
// disabled button. A price change alone does not block: checkout asks the
// customer to accept the new price explicitly.
//
// Redesign Batch 6: Stitch cart composition (line cards left, lavender
// summary panel right, sticky below the 64px header from 1024px only).
// The Stitch subtotal / shipping / tax / total rows, discount code and
// payment logos are NOT reproduced: CartRead has no such values, ADR-024
// forbids a shipping charge, and there is no coupon contract.
export function CartPage({
  cart,
  isLoading = false,
  isError = false,
  onRetry,
  onQuantityChange,
  onRemove,
  pendingProductIds = NO_PENDING,
  lineErrors = {},
  notice,
  canCheckout = true,
}: CartPageProps) {
  if (isLoading) {
    return (
      <div role="status" className={GRID_CLASSES}>
        <span className="sr-only">Loading your cart…</span>
        <div aria-hidden="true" className="flex flex-col gap-4 desktop:col-span-8">
          {[0, 1].map((index) => (
            <div
              key={index}
              className="h-44 animate-pulse rounded-card bg-surface-container-low motion-reduce:animate-none"
            />
          ))}
        </div>
        <div
          aria-hidden="true"
          className="h-64 animate-pulse rounded-panel bg-surface-container-low motion-reduce:animate-none desktop:col-span-4"
        />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex max-w-2xl flex-col items-start gap-4">
        <Alert variant="error" message="We couldn't load your cart. Please try again." />
        {onRetry && (
          <Button type="button" onClick={onRetry}>
            Retry
          </Button>
        )}
      </div>
    );
  }

  const lines = cart?.lines ?? [];
  const lineIds = new Set(lines.map((line) => line.productId));
  const orphanErrors = Object.entries(lineErrors).filter(([productId]) => !lineIds.has(productId));

  return (
    <div className="flex flex-col gap-6">
      {notice && <Alert variant="info" message={notice} />}
      {orphanErrors.map(([productId, message]) => (
        <Alert key={productId} variant="error" message={message} />
      ))}

      {lines.length === 0 ? (
        <div className="flex flex-col items-center rounded-card border border-dashed border-outline-variant bg-surface-container-lowest px-4 pb-12">
          <EmptyState message="Your cart is empty." icon="shopping-cart" />
          <Link href="/shop" className={buttonLinkClassName("primary", "lg")}>
            Browse the shop
          </Link>
        </div>
      ) : (
        <div className={GRID_CLASSES}>
          <ul aria-label="Cart items" className="flex min-w-0 flex-col gap-4 desktop:col-span-8">
            {lines.map((line) => (
              <li key={line.productId}>
                <CartLineItem
                  line={line}
                  pending={pendingProductIds.has(line.productId)}
                  errorMessage={lineErrors[line.productId]}
                  onQuantityChange={onQuantityChange}
                  onRemove={onRemove}
                />
              </li>
            ))}
          </ul>

          <CartSummary cart={cart!} canCheckout={canCheckout} />
        </div>
      )}
    </div>
  );
}

function CartSummary({ cart, canCheckout }: { cart: CartModel; canCheckout: boolean }) {
  const count = cartItemCount(cart);
  const blocked = cartBlockingLines(cart).length > 0;
  const priceChanged = cart.lines.some((line) => line.priceChanged);
  const ready = canCheckout && !blocked;
  return (
    <section
      aria-labelledby="cart-summary-heading"
      className="flex flex-col gap-6 rounded-panel border border-outline-variant/20 bg-surface-container-low p-6 tablet:p-8 desktop:sticky desktop:top-24 desktop:col-span-4"
    >
      <h2 id="cart-summary-heading" className="font-headline text-headline-md text-on-surface">
        Cart summary
      </h2>
      <dl className="flex flex-col gap-3 border-b border-outline-variant/30 pb-6">
        <div className="flex items-baseline justify-between gap-4">
          <dt className="text-body-md text-on-surface-variant">Items</dt>
          <dd className="font-label text-label-caps font-bold tabular-nums text-on-surface">
            {count} item{count === 1 ? "" : "s"}
          </dd>
        </div>
      </dl>
      <p className="flex items-start gap-2 text-xs text-on-surface-variant">
        <Icon name="receipt-long" className="mt-px h-4 w-4 text-outline" />
        <span>Your total is calculated at checkout from current prices.</span>
      </p>
      {blocked && (
        <p className="flex items-start gap-2 rounded-control border border-warning-outline bg-warning-container px-3 py-2 text-xs text-on-warning-container">
          <Icon name="warning" className="mt-px h-4 w-4" />
          <span>Some items need your attention before you can check out.</span>
        </p>
      )}
      {!blocked && priceChanged && (
        <p className="flex items-start gap-2 rounded-control border border-info-outline bg-info-container px-3 py-2 text-xs text-on-info-container">
          <Icon name="info" className="mt-px h-4 w-4 text-info" />
          <span>Some prices have changed. You&apos;ll confirm the new prices at checkout.</span>
        </p>
      )}
      <div className="flex flex-col gap-3">
        {ready ? (
          <Link href="/checkout" className={`${buttonLinkClassName("primary", "lg")} w-full`}>
            Proceed to checkout
            <Icon name="arrow-forward" className="h-4 w-4" />
          </Link>
        ) : (
          <Button type="button" size="lg" className="w-full" disabled>
            Proceed to checkout
          </Button>
        )}
        <Link
          href="/shop"
          className="self-center rounded-badge px-2 py-2.5 text-xs font-semibold text-primary underline-offset-4 hover:underline"
        >
          Continue shopping
        </Link>
      </div>
    </section>
  );
}
