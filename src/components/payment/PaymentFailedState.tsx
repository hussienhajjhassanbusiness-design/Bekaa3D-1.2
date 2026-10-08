import type { ReactNode } from "react";

export interface PaymentFailedStateProps {
  // Only ever a caller-supplied, already-valid action — no invented
  // working Checkout/Cart link.
  actionSlot?: ReactNode;
}

// #FVS027 — safe retry guidance only. Never claims a provider-
// specific reason (e.g. "card declined") unless the backend confirms
// one — none does today.
export function PaymentFailedState({ actionSlot }: PaymentFailedStateProps) {
  return (
    <div className="flex flex-col items-center gap-3 py-8 text-center">
      <p className="text-h3 font-bold text-text-primary">Your payment could not be completed.</p>
      <p className="text-body text-text-secondary">You have not been charged. You can try again.</p>
      {actionSlot && <div className="mt-2">{actionSlot}</div>}
    </div>
  );
}
