// Optional Stitch price roles (COMPONENT-SPECS §17). Omitted = no classes:
// the price inherits the typography of its surroundings.
export type PriceDisplaySize = "card" | "summary" | "detail";

export interface PriceDisplayProps {
  amountCents: number;
  currency: string;
  locale?: string;
  size?: PriceDisplaySize;
}

const SIZE_CLASSES: Record<PriceDisplaySize, string> = {
  // Product card: Hanken 20/600 primary.
  card: "font-headline text-headline-md text-primary tabular-nums",
  // Order summary total: Hanken 32/700 primary.
  summary: "font-headline text-headline-lg text-primary tabular-nums",
  // Product detail hero: Hanken 48/800 primary (36px below 768).
  detail: "font-display text-display text-primary tabular-nums",
};

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
export function PriceDisplay({ amountCents, currency, locale, size }: PriceDisplayProps) {
  const formatted = new Intl.NumberFormat(locale, { style: "currency", currency }).format(amountCents / 100);
  return <span className={size ? SIZE_CLASSES[size] : undefined}>{formatted}</span>;
}
