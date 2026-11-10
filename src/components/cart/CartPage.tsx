import Link from "next/link";
import { Alert } from "@/components/feedback/Alert";
import { Button } from "@/components/forms/Button";
import { EmptyState } from "@/components/feedback/EmptyState";
import { cartNeedsAttention } from "@/lib/cart/cartInvariants";
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
}

const NO_PENDING: ReadonlySet<string> = new Set();

// #FVS025-CART-PAGE
//
// Presentational: loading / error / empty / populated. The summary has a
// unit count only. CartRead has no total, so none is shown or computed;
// checkout recomputes it from live prices. There is no checkout link:
// /checkout does not exist yet (FVS-026), so the CTA area says so plainly.
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

          <CartSummary cart={cart!} />
        </div>
      )}
    </div>
  );
}

function CartSummary({ cart }: { cart: CartModel }) {
  const count = cartItemCount(cart);
  return (
    <section
      aria-label="Cart summary"
      className="flex h-fit flex-col gap-3 rounded-md border border-border-default bg-white p-4"
    >
      <h2 className="text-h4 font-semibold text-text-primary">Summary</h2>
      <p className="text-body text-text-primary">
        {count} item{count === 1 ? "" : "s"}
      </p>
      <p className="text-caption text-text-secondary">
        Your total is calculated at checkout from current prices.
      </p>
      {cartNeedsAttention(cart) && (
        <p className="rounded-md border-l-4 border-l-warning bg-warning-bg px-3 py-2 text-caption text-text-primary">
          Some items need your attention before you can check out.
        </p>
      )}
      <p className="rounded-md bg-neutral-50 px-3 py-2 text-caption text-text-secondary">
        Online checkout isn&apos;t available yet.
      </p>
    </section>
  );
}
