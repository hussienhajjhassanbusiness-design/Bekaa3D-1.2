import { Button } from "@/components/forms/Button";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { canAdjustQuantity, hasPriceChanged } from "@/lib/cart/cartInvariants";
import type { CartLineModel } from "@/lib/cart/cartModel";

export interface CartLineItemProps {
  line: CartLineModel;
  // Required, presentational-only seams — mirrors AddressList.onDelete's
  // precedent. Wired to a real mutation only once
  // FVS-025-IMPLEMENTATION-PLAN.md T08 unblocks.
  onQuantityChange: (lineId: string, nextQuantity: number) => void;
  onRemove: (lineId: string) => void;
  // Caller-supplied, already-safe text — never a hardcoded/invented
  // backend enum (the unavailable-line mechanism is unconfirmed).
  unavailableNotice?: string;
}

// #FVS025-CART-LINE-ITEM
//
// Presentational only — no network, no query. STL lines never render
// a stepper at all (quantity is structurally fixed at 1,
// #SECURITY-CART-SERVER-AUTHORITY); physical increment/decrement
// buttons carry the product name in their accessible name and the
// current quantity is announced via a live region. A price-snapshot
// divergence shows both prices plus a note — never silently
// replacing one with the other. Reuses PriceDisplay directly (no
// duplicated currency formatting).
export function CartLineItem({ line, onQuantityChange, onRemove, unavailableNotice }: CartLineItemProps) {
  const adjustable = canAdjustQuantity(line);
  const priceChanged = hasPriceChanged(line);
  const atMax = line.maxQuantity !== undefined && line.quantity >= line.maxQuantity;
  // Reaching 0 via the stepper is never valid — Remove is the
  // explicit action for dropping a line entirely.
  const atMin = line.quantity <= 1;

  return (
    <div className="flex flex-col gap-2 rounded-md border border-border-default p-4">
      <div className="flex items-start justify-between gap-2">
        <span className="text-body text-text-primary">{line.productDisplayName}</span>
        <div className="text-right">
          <PriceDisplay amountCents={line.snapshotPriceCents} currency={line.currency} />
          {priceChanged && (
            <div className="mt-1">
              <PriceDisplay amountCents={line.currentPriceCents!} currency={line.currency} />
              <p className="text-caption text-warning">Price updated</p>
            </div>
          )}
        </div>
      </div>

      {unavailableNotice && (
        <p role="alert" className="text-caption text-danger">
          {unavailableNotice}
        </p>
      )}

      {adjustable ? (
        <div className="flex items-center gap-2">
          <Button
            type="button"
            onClick={() => onQuantityChange(line.id, line.quantity - 1)}
            disabled={atMin}
            aria-label={`Decrease quantity of ${line.productDisplayName}`}
          >
            −
          </Button>
          <span role="status">{line.quantity}</span>
          <Button
            type="button"
            onClick={() => onQuantityChange(line.id, line.quantity + 1)}
            disabled={atMax}
            aria-label={`Increase quantity of ${line.productDisplayName}`}
          >
            +
          </Button>
        </div>
      ) : (
        <p className="text-caption text-text-secondary">Qty: {line.quantity}</p>
      )}

      <div>
        <Button type="button" onClick={() => onRemove(line.id)}>
          Remove
        </Button>
      </div>
    </div>
  );
}
