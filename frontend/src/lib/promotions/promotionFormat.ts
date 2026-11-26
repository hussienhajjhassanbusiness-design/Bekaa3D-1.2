import type { DiscountType, PromotionScope, PromotionStatus } from "./promotionTypes";
import type { StatusBadgeTone } from "@/components/admin/StatusBadge";

// #SHARED-PROMOTION-LABELS
//
// Display labels only. These turn the server's `discount_type` /
// `discount_value` into "20% OFF" or "$5 OFF" — they never produce a price.
// The price a customer pays is always the server's own `price` field
// (bekaa3d-commerce-ux: server-authoritative totals).

function money(cents: number, currency: string, locale?: string): string {
  const whole = cents % 100 === 0;
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    minimumFractionDigits: whole ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(cents / 100);
}

/** "20%" or "$5" / "$5.50". */
export function discountAmount(type: DiscountType, value: number, currency: string, locale?: string): string {
  return type === "percentage" ? `${value}%` : money(value, currency, locale);
}

/** The banner's large text: "20% OFF". */
export function discountHeadline(type: DiscountType, value: number, currency: string, locale?: string): string {
  return `${discountAmount(type, value, currency, locale)} OFF`;
}

/** The product card's corner badge: "-20%". */
export function discountBadge(type: DiscountType, value: number, currency: string, locale?: string): string {
  return `-${discountAmount(type, value, currency, locale)}`;
}

const SCOPE_LABELS: Record<PromotionScope, string> = {
  all: "All products",
  physical: "Physical products",
  stl: "STL files",
  selected: "Selected products",
};

export function promotionScopeLabel(scope: PromotionScope): string {
  return SCOPE_LABELS[scope];
}

const SCOPE_PHRASES: Record<PromotionScope, string> = {
  all: "on everything in the shop",
  physical: "on physical prints",
  stl: "on STL files",
  selected: "on selected products",
};

export function promotionScopePhrase(scope: PromotionScope): string {
  return SCOPE_PHRASES[scope];
}

const STATUS: Record<PromotionStatus, { label: string; tone: StatusBadgeTone }> = {
  active: { label: "Active", tone: "positive" },
  scheduled: { label: "Scheduled", tone: "info" },
  ended: { label: "Ended", tone: "neutral" },
  inactive: { label: "Inactive", tone: "warning" },
};

export function describePromotionStatus(status: PromotionStatus): { label: string; tone: StatusBadgeTone } {
  return STATUS[status];
}

export function formatPromotionDate(iso: string, locale?: string): string {
  return new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric" }).format(new Date(iso));
}
