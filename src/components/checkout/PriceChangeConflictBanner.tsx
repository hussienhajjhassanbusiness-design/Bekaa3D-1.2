import { Button } from "@/components/forms/Button";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import type { PriceChangeLine } from "@/lib/checkout/checkoutErrors";

export interface PriceChangeConflictBannerProps {
  // From the 409 CART_PRICE_CHANGED `price_changes` extension.
  changes: readonly PriceChangeLine[];
  // productId -> name, from the canonical cart.
  names: Readonly<Record<string, string>>;
  accepted: boolean;
  onAccept: () => void;
}

const UNKNOWN_PRODUCT = "A product in your cart";

// #SECURITY-CHECKOUT-PRICE-CONFIRMATION
//
// The server refused the checkout because live prices differ from the
// cart's snapshot; nothing was charged. The customer must accept the new
// prices explicitly: onAccept is called only from the button, never on
// mount or on a re-render, and the caller resubmits only when the customer
// then places the order. Old and new prices are shown side by side, never
// subtracted into a delta.
export function PriceChangeConflictBanner({ changes, names, accepted, onAccept }: PriceChangeConflictBannerProps) {
  if (accepted) {
    return (
      <p role="status" className="rounded-md border-l-4 border-l-info bg-info-bg p-4 text-body text-text-primary">
        You&apos;ve accepted the new prices. Place your order to continue.
      </p>
    );
  }

  return (
    <div role="alert" aria-live="assertive" className="rounded-md border border-danger bg-danger-bg p-4">
      <p className="text-body font-semibold text-danger">
        Some prices have changed since you added these items. Nothing has been charged.
      </p>
      <ul className="mt-2 flex flex-col gap-2">
        {changes.map((change) => (
          <li
            key={change.productId}
            className="flex flex-wrap items-center justify-between gap-2 text-body text-text-primary"
          >
            <span>{names[change.productId] ?? UNKNOWN_PRODUCT}</span>
            <span className="flex items-center gap-2">
              <span className="sr-only">was</span>
              <span className="text-text-secondary line-through">
                <PriceDisplay amountCents={change.oldAmountCents} currency={change.currency} />
              </span>
              <span aria-hidden="true">→</span>
              <span className="sr-only">now</span>
              <PriceDisplay amountCents={change.newAmountCents} currency={change.currency} />
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-caption text-text-secondary">
        Accept the new prices to continue, or go back to your cart to change your order.
      </p>
      <Button type="button" onClick={onAccept} className="mt-3">
        Accept new prices
      </Button>
    </div>
  );
}
