import { Button } from "@/components/forms/Button";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import type { PriceConflictLine } from "@/lib/checkout/checkoutModels";

export interface PriceChangeConflictBannerProps {
  lines: readonly PriceConflictLine[];
  onReconfirm: () => void;
}

// #SECURITY-CHECKOUT-PRICE-CONFIRMATION
//
// Blocks progress — announced via aria-live="assertive" per the
// source's own accessibility line. Never auto-retries: onReconfirm is
// the only callback this component ever calls, and only on an
// explicit click. The old and new price are shown side by side via
// PriceDisplay (reused) — never subtracted into a delta.
export function PriceChangeConflictBanner({ lines, onReconfirm }: PriceChangeConflictBannerProps) {
  return (
    <div role="alert" aria-live="assertive" className="rounded-md border border-danger bg-danger-bg p-4">
      <p className="text-body font-semibold text-danger">Some prices have changed since you added these items.</p>
      <ul className="mt-2 flex flex-col gap-2">
        {lines.map((line) => (
          <li key={line.lineId} className="flex items-center justify-between gap-2 text-body text-text-primary">
            <span>{line.productDisplayName}</span>
            <span className="flex items-center gap-2">
              <PriceDisplay amountCents={line.oldPriceCents} currency={line.currency} />
              <span aria-hidden="true">→</span>
              <PriceDisplay amountCents={line.newPriceCents} currency={line.currency} />
            </span>
          </li>
        ))}
      </ul>
      <Button type="button" onClick={onReconfirm} className="mt-3">
        Reconfirm
      </Button>
    </div>
  );
}
