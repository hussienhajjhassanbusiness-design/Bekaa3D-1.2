import { Icon } from "@/components/ui/Icon";

export interface CheckoutDisabledBannerProps {
  // Already-resolved text from a future adapter — never a guessed
  // acceptingOrders/isCheckoutEnabled settings field name. The real
  // public-settings mapping stays backend-gated
  // (FVS-026-IMPLEMENTATION-PLAN.md §0).
  reason: string;
}

// #FVS026 — the kill-switch banner. No doomed request is ever made:
// this component renders only text a parent already has.
// Redesign Batch 6: error callout card (icon + text).
export function CheckoutDisabledBanner({ reason }: CheckoutDisabledBannerProps) {
  return (
    <p
      role="alert"
      className="flex items-start gap-3 rounded-card border border-error/20 bg-error-container p-4 text-sm text-on-error-container"
    >
      <Icon name="error" className="h-5 w-5 text-error" />
      <span className="min-w-0">{reason}</span>
    </p>
  );
}
