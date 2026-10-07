export interface PriceDisplayProps {
  amountCents: number;
  currency: string;
  locale?: string;
}

// #SHARED-PRICE-DISPLAY
//
// Display-only — never parses money (MoneyInput owns that) and never
// computes a new monetary amount. `amountCents` is the untouched
// integer-cents domain value (vertical-slice-plan.md's own global
// "Money uses integer cents" rule); the single division by 100 exists
// only because Intl.NumberFormat's `style: "currency"` API expects a
// major-unit number, and Intl.NumberFormat rounds to the currency's
// correct minor-unit digits, so it produces no visible artifact.
//
// `currency` is always required and explicit — never hardcoded, since
// vertical-slice-plan.md §2 lists USD settlement itself as a still-open
// external item. `locale` defaults to the runtime's own default locale
// when omitted — a generic fallback, not a silently-adopted business
// rule; a confirmed product locale, once one exists, is passed in by
// the caller.
export function PriceDisplay({ amountCents, currency, locale }: PriceDisplayProps) {
  const formatted = new Intl.NumberFormat(locale, { style: "currency", currency }).format(amountCents / 100);
  return <span>{formatted}</span>;
}
