export interface CheckoutDisabledBannerProps {
  // Already-resolved text from a future adapter — never a guessed
  // acceptingOrders/isCheckoutEnabled settings field name. The real
  // public-settings mapping stays backend-gated
  // (FVS-026-IMPLEMENTATION-PLAN.md §0).
  reason: string;
}

// #FVS026 — the kill-switch banner. No doomed request is ever made:
// this component renders only text a parent already has.
export function CheckoutDisabledBanner({ reason }: CheckoutDisabledBannerProps) {
  return (
    <p role="alert" className="rounded-md border border-danger bg-danger-bg p-4 text-body text-danger">
      {reason}
    </p>
  );
}
