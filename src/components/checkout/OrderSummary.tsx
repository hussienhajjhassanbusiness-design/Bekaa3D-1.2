import { PriceDisplay } from "@/components/catalog/PriceDisplay";

export interface OrderSummaryProps {
  // Every amount field is optional — no source confirms the checkout
  // response's exact field names yet (only the concept that the
  // server computes trusted shipping/totals,
  // FVS-026-IMPLEMENTATION-PLAN.md §0). `currency` alone is required,
  // never hardcoded.
  subtotalCents?: number;
  shippingCents?: number;
  totalCents?: number;
  currency: string;
}

const PLACEHOLDER = "Order total will be confirmed at submission.";

// #SECURITY-SERVER-CHECKOUT-TOTALS
//
// Display-only — this component NEVER sums line items or infers one
// amount field from the others. If, say, `shippingCents` is omitted,
// it stays omitted; nothing here computes it.
export function OrderSummary({ subtotalCents, shippingCents, totalCents, currency }: OrderSummaryProps) {
  const hasAnyAmount = subtotalCents !== undefined || shippingCents !== undefined || totalCents !== undefined;

  if (!hasAnyAmount) {
    return <p className="text-body text-text-secondary">{PLACEHOLDER}</p>;
  }

  return (
    <dl className="flex flex-col gap-2">
      {subtotalCents !== undefined && (
        <div className="flex items-center justify-between gap-2">
          <dt className="text-body text-text-secondary">Subtotal</dt>
          <dd>
            <PriceDisplay amountCents={subtotalCents} currency={currency} />
          </dd>
        </div>
      )}
      {shippingCents !== undefined && (
        <div className="flex items-center justify-between gap-2">
          <dt className="text-body text-text-secondary">Shipping</dt>
          <dd>
            <PriceDisplay amountCents={shippingCents} currency={currency} />
          </dd>
        </div>
      )}
      {totalCents !== undefined && (
        <div className="flex items-center justify-between gap-2">
          <dt className="text-body font-semibold text-text-primary">Total</dt>
          <dd className="font-semibold">
            <PriceDisplay amountCents={totalCents} currency={currency} />
          </dd>
        </div>
      )}
    </dl>
  );
}
