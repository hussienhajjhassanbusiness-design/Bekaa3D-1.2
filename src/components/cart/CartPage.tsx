import Link from "next/link";
import { Alert } from "@/components/feedback/Alert";
import { Button } from "@/components/forms/Button";
import { EmptyState } from "@/components/feedback/EmptyState";
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

// #FVS025-CART-PAGE
//
// Presentational: loading / error / empty / populated. The summary has a
// unit count only. CartRead has no total, so none is shown or computed;
// checkout recomputes it from live prices. Phase 5D: the checkout CTA links
// to /checkout (FVS-026) only when the cart can proceed; otherwise it is a
// disabled button. A price change alone does not block: checkout asks the
// customer to accept the new price explicitly.
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
      <div role="status" className="flex flex-col gap-4">
        <span className="sr-only">Loading your cart…</span>
        {[0, 1].map((index) => (
          <div
            key={index}
            aria-hidden="true"
            className="h-32 animate-pulse rounded-md bg-neutral-200 motion-reduce:animate-none"
          />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-start gap-3">
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
        <div className="flex flex-col items-center">
          <EmptyState message="Your cart is empty." />
          <Link
            href="/shop"
            className="rounded-md bg-brand-dark-green px-4 py-2 text-text-on-brand hover:bg-brand-green"
          >
            Browse the shop
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 desktop:grid-cols-[1fr_20rem]">
          <ul aria-label="Cart items" className="flex flex-col gap-4">
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
      aria-label="Cart summary"
      className="flex h-fit flex-col gap-3 rounded-md border border-border-default bg-white p-4"
    >
      <h2 className="text-h4 font-semibold text-text-primary">Summary</h2>
      <p className="text-body text-text-primary">
        {count} item{count === 1 ? "" : "s"}
      </p>
      <p className="text-caption text-text-secondary">Your total is calculated at checkout from current prices.</p>
      {blocked && (
        <p className="rounded-md border-l-4 border-l-warning bg-warning-bg px-3 py-2 text-caption text-text-primary">
          Some items need your attention before you can check out.
        </p>
      )}
      {!blocked && priceChanged && (
        <p className="rounded-md bg-neutral-50 px-3 py-2 text-caption text-text-secondary">
          Some prices have changed. You&apos;ll confirm the new prices at checkout.
        </p>
      )}
      {ready ? (
        <Link
          href="/checkout"
          className="rounded-md bg-brand-dark-green px-4 py-2 text-center font-semibold text-text-on-brand hover:bg-brand-green"
        >
          Proceed to checkout
        </Link>
      ) : (
        <Button type="button" disabled>
          Proceed to checkout
        </Button>
      )}
    </section>
  );
}
