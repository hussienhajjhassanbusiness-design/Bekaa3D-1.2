import { PriceDisplay } from "@/components/catalog/PriceDisplay";

export interface OrderSummaryProps {
  // Every amount field is optional — no source confirms the checkout
  // response's exact field names yet (only the concept that the
  // server computes trusted totals, FVS-026-IMPLEMENTATION-PLAN.md
  // §0). `currency` alone is required, never hardcoded. No
  // `shippingCents` field: ADR-024 means nothing is ever charged for
  // shipping on this site.
  subtotalCents?: number;
  totalCents?: number;
  currency: string;
  // Presentation only (redesign Batch 6, checkout confirmation): the total
  // row in the Stitch summary-total role. Omitted = unchanged rendering,
  // so the account Orders page is untouched until its own batch.
  emphasis?: boolean;
}

const PLACEHOLDER = "Order total will be confirmed at submission.";

// #SECURITY-SERVER-CHECKOUT-TOTALS
//
// Display-only — this component NEVER sums line items or infers one
// amount field from the others. If, say, `subtotalCents` is omitted,
// it stays omitted; nothing here computes it.
export function OrderSummary({ subtotalCents, totalCents, currency, emphasis = false }: OrderSummaryProps) {
  const hasAnyAmount = subtotalCents !== undefined || totalCents !== undefined;

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
      {totalCents !== undefined && (
        <div className="flex items-center justify-between gap-2">
          <dt
            className={
              emphasis ? "font-headline text-headline-md text-on-surface" : "text-body font-semibold text-text-primary"
            }
          >
            Total
          </dt>
          <dd className={emphasis ? undefined : "font-semibold"}>
            <PriceDisplay amountCents={totalCents} currency={currency} size={emphasis ? "summary" : undefined} />
          </dd>
        </div>
      )}
    </dl>
  );
}
