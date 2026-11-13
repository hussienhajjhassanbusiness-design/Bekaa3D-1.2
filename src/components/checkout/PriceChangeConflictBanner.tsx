import { Button } from "@/components/forms/Button";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { Icon } from "@/components/ui/Icon";
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
const LABEL_CLASSES = "font-label text-label-sm uppercase tracking-widest text-on-surface-variant";

// #SECURITY-CHECKOUT-PRICE-CONFIRMATION
//
// The server refused the checkout because live prices differ from the
// cart's snapshot; nothing was charged. The customer must accept the new
// prices explicitly: onAccept is called only from the button, never on
// mount or on a re-render, and the caller resubmits only when the customer
// then places the order. Old and new prices are shown side by side, never
// subtracted into a delta.
//
// Redesign Batch 6: a warning card with one row per changed line and
// VISIBLE "Was" / "Now" labels (the strike-through is decoration only), so
// the change is never conveyed by colour or styling alone.
export function PriceChangeConflictBanner({ changes, names, accepted, onAccept }: PriceChangeConflictBannerProps) {
  if (accepted) {
    return (
      <p
        role="status"
        className="flex items-start gap-3 rounded-card border border-info-outline bg-info-container p-4 text-body text-on-info-container"
      >
        <Icon name="check-circle" className="h-5 w-5 text-info" />
        <span>You&apos;ve accepted the new prices. Place your order to continue.</span>
      </p>
    );
  }

  return (
    <div
      role="alert"
      aria-live="assertive"
      className="flex flex-col gap-4 rounded-card border border-warning-outline bg-warning-container p-4 text-on-warning-container tablet:p-5"
    >
      <p className="flex items-start gap-3 text-body font-semibold">
        <Icon name="warning" className="h-5 w-5" />
        <span>Some prices have changed since you added these items. Nothing has been charged.</span>
      </p>
      <ul className="flex flex-col divide-y divide-outline-variant/40 rounded-control border border-warning-outline bg-surface-container-lowest text-on-surface">
        {changes.map((change) => (
          <li key={change.productId} className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 p-3">
            <span className="min-w-0 break-words text-body font-semibold">
              {names[change.productId] ?? UNKNOWN_PRODUCT}
            </span>
            <span className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
              <span className="flex items-baseline gap-2">
                <span className={LABEL_CLASSES}>Was</span>
                <span className="text-body text-on-surface-variant line-through decoration-1">
                  <PriceDisplay amountCents={change.oldAmountCents} currency={change.currency} />
                </span>
              </span>
              <Icon name="arrow-forward" className="h-4 w-4 self-center text-outline" />
              <span className="flex items-baseline gap-2">
                <span className={LABEL_CLASSES}>Now</span>
                <span className="text-body font-bold tabular-nums">
                  <PriceDisplay amountCents={change.newAmountCents} currency={change.currency} />
                </span>
              </span>
            </span>
          </li>
        ))}
      </ul>
      <p className="text-caption">Accept the new prices to continue, or go back to your cart to change your order.</p>
      <Button type="button" onClick={onAccept} className="self-start">
        Accept new prices
      </Button>
    </div>
  );
}
